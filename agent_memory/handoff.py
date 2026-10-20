"""The hooks that keep the notes current. Conventions alone rely on the agent remembering to write, and it
doesn't: an audit of these notes found every miss was a fact nobody had written down. So:

    stop         Stop: a session that changed things is sent back once to update NOW.md and LOG.md
    prompt       UserPromptSubmit: a message that sounds like a decision gets a reminder to record it
    pre-write    PreToolUse (Write): LOG.md is append-only; a whole-file Write of it is denied
    pre-compact  PreCompact: a LOG line marks the compaction and names the transcript

Each one only nudges or guards; none can trap a session. Every hook reads the event JSON on stdin.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .config import Config

MIN_WORK = 3  # edits + commits before a session with no LOG line is sent back

STATE_FILE = re.compile(r"(?:^|[/\\\s\"'])(NOW|LOG)\.md\b")
# A redirect only writes the state file when the file is its target: `cat NOW.md 2>/dev/null` and
# `head NOW.md 2>&1` are reads. 2> (stderr) and >& (a descriptor) never are. A quoted target may have spaces.
REDIRECT_TO_STATE = re.compile(
    r"""(?<!\d)>>?(?!&)\s*(?:"[^"\n]*[/\\]|'[^'\n]*[/\\]|["']?(?:[^\s;|&<>"']*[/\\])?)(?:NOW|LOG)\.md\b""")
SHELL_WRITE = re.compile(r"\btee\b|sed\s+-i|\.write\(|write_text\(|Add-Content|Out-File|Set-Content")
COMMIT = re.compile(r"\bgit\b[^\n|;&]*\bcommit\b")
DECISION = re.compile(
    r"\b(?:leave (?:it|that|this|them|those)|as[- ]is|(?:is|that'?s|it'?s|are) final|final(?:ly)? decision|decided|"
    r"let'?s not|do(?: not|n'?t) (?:bother|do|change|touch|add|use|squash|push|worry|make|run|need)|"
    r"not (?:going to|gonna|doing)|won'?t|skip (?:it|that|this|the)|hold off|never ?mind|never\b|"
    r"scrap (?:it|that|this)|drop (?:it|that|this)|no need|instead|actually|i(?:'?ll| will)|for now|later|"
    r"when (?:it|that|he|she|they)(?:'?s| is| are) done|waiting (?:on|for))\b",
    re.I)
PASTED = re.compile(r"<pasted_content\b.*?</pasted_content[^>]*>", re.S)


def tag(session_id: str) -> str:
    return "s:" + session_id[:8]


def _entries(transcript_path: str):
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        if '"tool_use"' not in line and '"tool_result"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(entry, dict) and not entry.get("isSidechain") and isinstance(content, list):
            yield entry.get("type"), [b for b in content if isinstance(b, dict)]


def tool_calls(transcript_path: str):
    """Every tool call the session itself made (not its subagents), in order, as (name, input). A call whose
    result was an error (refused for permissions, a failed command) changed nothing and is left out."""
    entries = list(_entries(transcript_path) or ())
    failed = {b.get("tool_use_id") for kind, blocks in entries if kind == "user"
              for b in blocks if b.get("type") == "tool_result" and b.get("is_error")}
    for kind, blocks in entries:
        if kind != "assistant":
            continue
        for block in blocks:
            if block.get("type") == "tool_use" and block.get("id") not in failed:
                yield block.get("name", ""), block.get("input") or {}


def classify(name: str, tool_input: dict) -> str | None:
    """'state' = wrote NOW.md or LOG.md, 'commit', 'edit' = changed some other file, else None."""
    if name in ("Edit", "Write", "NotebookEdit"):
        return "state" if STATE_FILE.search(str(tool_input.get("file_path", ""))) else "edit"
    if name in ("Bash", "PowerShell"):
        command = str(tool_input.get("command", ""))
        if REDIRECT_TO_STATE.search(command) or (STATE_FILE.search(command) and SHELL_WRITE.search(command)):
            return "state"  # one command can commit and then log; the log is what the gate cares about
        if COMMIT.search(command):
            return "commit"
    return None


def work_summary(transcript_path: str) -> dict:
    """Counts for the whole session, and for the stretch since it last wrote a state file."""
    total = {"edit": 0, "commit": 0}
    since = {"edit": 0, "commit": 0}
    wrote_state = False
    for name, tool_input in tool_calls(transcript_path) or ():
        kind = classify(name, tool_input)
        if kind == "state":
            wrote_state = True
            since = {"edit": 0, "commit": 0}
        elif kind:
            total[kind] += 1
            since[kind] += 1
    return {"total": total, "since": since, "wrote_state": wrote_state}


HOOK_SURFACE = "Claude Code (hook)"  # pre_compact's lines: the hook's record, not the session's


def session_lines(text: str) -> list[str]:
    """LOG lines a session wrote itself. pre_compact's line carries the session's tag too, and counting it
    would switch off the Stop gate and the audit for exactly the long sessions that compact."""
    return [line for line in text.splitlines() if f"· {HOOK_SURFACE} ·" not in line]


def logged(cfg: Config, session_id: str) -> bool:
    try:
        text = cfg.log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(tag(session_id) in line for line in session_lines(text))


def stop(cfg: Config, event: dict) -> dict | None:
    """Send the session back once when it has (a) made MIN_WORK edits or commits and has no LOG line, or
    (b) committed since it last wrote NOW.md or LOG.md. Never twice in a row (stop_hook_active), and the
    message lets it answer "nothing worth recording", so it nudges and cannot trap."""
    if event.get("stop_hook_active"):
        return None
    sid, transcript = event.get("session_id") or "", event.get("transcript_path") or ""
    if not sid or not transcript:
        return None
    work = work_summary(transcript)
    total = work["total"]["edit"] + work["total"]["commit"]
    if total >= MIN_WORK and not logged(cfg, sid):
        why = (f"This session has made {work['total']['edit']} edit(s) and {work['total']['commit']} commit(s), "
               f"and LOG.md has no line tagged {tag(sid)}.")
    elif work["since"]["commit"]:
        why = (f"This session has committed {work['since']['commit']} time(s) since it last wrote NOW.md or LOG.md "
               f"({work['since']['edit']} other edit(s) in that stretch).")
    else:
        return None
    return {"decision": "block", "reason": (
        f"{why} Before stopping, write it down: update the project's NOW.md in its root (State, Next, Decisions "
        "including anything decided against, Open threads and who each waits on, anything claimed but not verified) "
        f"and add one line to the END of {cfg.log_file}, ending with {tag(sid)} (append; never rewrite that file). "
        "Then add ONE line saying what you recorded; do not repeat the reply you already gave. If nothing since the "
        "last write changes what a fresh session would need to know, say so in one line and stop.")}


def decision_note(prompt: str | None) -> str | None:
    found = DECISION.search(PASTED.sub("", prompt or ""))
    if not found:
        return None
    return (f"This message may settle something (it says \"{found.group(0)}\"). If it decides anything, especially "
            "NOT to do something, calls something final, or leaves something waiting on someone, record that in the "
            "project's NOW.md under Decisions or Open threads in this turn, not at the end.")


def prompt(cfg: Config, event: dict) -> dict | None:
    note = decision_note(event.get("prompt"))
    if not note:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": note}}


def pre_write(cfg: Config, event: dict) -> dict | None:
    """A Write replaces a whole file. In the first live test of the Stop gate, a session told to add its line
    used Write and wiped every earlier line. Appending (>> in the shell, or Edit) is fine."""
    target = str((event.get("tool_input") or {}).get("file_path") or "")
    log = cfg.log_file
    if event.get("tool_name") != "Write" or not target or not log.exists():
        return None
    try:
        if Path(target).resolve() != log.resolve():
            return None
    except OSError:
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": f"{log} is append-only: Write would replace every earlier line. "
                                    "Add your line to the end instead (>> in the shell, or Edit)."}}


def pre_compact(cfg: Config, event: dict) -> None:
    """After compaction the session works from a summary; if NOW.md was not current, the only full record
    of what came before is the transcript, so the LOG line names it."""
    sid = event.get("session_id") or ""
    log = cfg.log_file
    if not sid or not log.exists():
        return None
    project = Path(event.get("cwd") or "").name or "?"
    line = (f"- {datetime.now():%Y-%m-%d} · {HOOK_SURFACE} · {project} · context compacted "
            f"({event.get('trigger', '?')}); anything not in NOW.md before this point is only in the transcript "
            f"{event.get('transcript_path', '?')} · {tag(sid)}\n")
    with log.open("a+", encoding="utf-8") as f:
        f.seek(0, 2)
        if f.tell():  # never glue the line onto a last line that has no newline
            f.seek(f.tell() - 1)
            if f.read(1) != "\n":
                line = "\n" + line
        f.write(line)
    return None


HOOKS = {"stop": stop, "prompt": prompt, "pre-write": pre_write, "pre-compact": pre_compact}
