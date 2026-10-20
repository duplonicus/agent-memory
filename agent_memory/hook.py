"""SessionStart hook: the brief a session starts from.

Prints, warnings first: this session's id and LOG tag, the global and project NOW.md clipped to a budget
(brief.py), a STALE warning when the repo has commits newer than its NOW.md, the last LOG lines, and the
sessions that did work without logging it. Files only: it works with the database down.

The project is the git root of the folder Claude was started in (else the folder itself), so start the
agent in the project's folder. In a git worktree, which has no NOW.md of its own, the main checkout's is used. A `cd` inside a running session changes nothing here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .audit import unlogged
from .brief import brief
from .config import Config

GLOBAL_CAP = 4000    # bytes the global NOW.md file should stay under: an index, not a history
PROJECT_CAP = 5000   # bytes for a project NOW.md: current state; history lives in LOG.md and git
HARNESS_CAP = 10000  # characters of hook output Claude Code shows in full
LOG_TAIL = 5


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def project_root(cwd: Path) -> tuple[Path, bool]:
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return (Path(top), True) if top else (cwd, False)


def session_start(cfg: Config, data: dict) -> str:
    sid = data.get("session_id", "")
    cwd = Path(data.get("cwd") or os.getcwd())
    root, is_repo = project_root(cwd)
    gnow = cfg.global_now
    pnow = (root / "NOW.md").resolve()
    if is_repo and not pnow.is_file():
        # A worktree has no NOW.md (it is untracked, in .git/info/exclude); the main checkout's is the
        # project's. --git-common-dir is the main .git, so its parent is the main checkout.
        common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if common and (Path(common).parent / "NOW.md").is_file():
            pnow = (Path(common).parent / "NOW.md").resolve()
    out: list[str] = []
    warn: list[str] = []
    if sid:
        out += ["=== this session ===", f"Session ID: {sid} (LOG.md tag: s:{sid[:8]})", ""]

    files = [(str(p), p.read_text(encoding="utf-8", errors="replace"))
             for p in dict.fromkeys([gnow, pnow]) if p.is_file()]
    if files:
        text = brief(files, cfg.brief_budget)
        clipped = "[+" in text
        if not clipped:
            text = text.replace(" (brief: items clipped, read the file for the rest)", "")
        out += [text, ""]
        if clipped:
            warn.append("!!! The NOW files below are a clipped brief ([+N chars] / [+N more items] mark the cuts). "
                        "Read the project NOW.md in full before changing anything it covers.")
    for p, cap in ((gnow, GLOBAL_CAP), (pnow, PROJECT_CAP)):
        if p.is_file() and p.stat().st_size > cap:
            warn.append(f"!!! OVERSIZE: {p} is {p.stat().st_size} bytes (cap {cap}). Move finished work out of it; "
                        f"LOG.md and git hold the history.")

    if pnow.is_file() and is_repo:
        last = _git(root, "log", "-1", "--format=%ct")
        now_ts = int(pnow.stat().st_mtime)
        if last and int(last) > now_ts + 300:
            n = _git(root, "rev-list", "--count", f"--since=@{now_ts}", "HEAD") or "?"
            warn.append(f"!!! STALE: {n} commit(s) in {root.name} are newer than its NOW.md. "
                        f"Check git log before trusting it, then bring it up to date.")
    elif is_repo and root != Path.home() and root.resolve() != cfg.notes_dir.resolve():
        out += [f"(No NOW.md for this repo: looked at {root / 'NOW.md'}. Create one from the template when there "
                f"is state worth keeping, and add /NOW.md and /state/ to .git/info/exclude.)", ""]

    if cfg.log_file.is_file():
        lines = [l for l in cfg.log_file.read_text(encoding="utf-8", errors="replace").splitlines() if l.startswith("- ")]
        if lines:
            out.append(f"=== last {min(LOG_TAIL, len(lines))} of {cfg.log_file} ===")
            out += [l if len(l) <= 300 else l[:260] + " [...] " + l[-12:] for l in lines[-LOG_TAIL:]]
            out.append("")

    missing = unlogged(cfg, skip=sid)
    if missing:
        out.append("=== sessions that changed things but have no LOG.md line ===")
        out += [f"{tag}  last active {when}  {folder}  ({n} edits/commits)" for when, tag, folder, n in missing]
        out += ["If you know what one of these did, add its LOG.md line (with its tag).", ""]

    body = "\n".join(out)
    if len(body) + sum(map(len, warn)) > HARNESS_CAP - 1000:
        warn.append(f"!!! This brief is {len(body)} characters; over {HARNESS_CAP} Claude Code shows only a preview. "
                    f"Trim the NOW.md files or lower [brief] budget.")
    head = ["=== warnings ===", *warn, ""] if warn else []
    return "\n".join(head) + body


def main(args: list[str] | None = None) -> None:
    """`agent-memory hook [session-start|stop|prompt|pre-write|pre-compact]`, event JSON on stdin."""
    from .config import load
    from .handoff import HOOKS
    which = (args or ["session-start"])[0]
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        data = {}
    if which == "session-start":
        try:
            print(session_start(load(), data))
        except Exception as e:  # noqa: BLE001 - a broken brief must never block a session
            print(f"(agent-memory brief failed: {type(e).__name__}: {e})")
        return
    if which not in HOOKS:
        print(f"agent-memory hook: unknown hook {which!r}", file=sys.stderr)
        return
    try:
        out = HOOKS[which](load(), data)
    except Exception:  # noqa: BLE001 - a broken hook must fail open, never block the session
        return
    if out:
        print(json.dumps(out))
