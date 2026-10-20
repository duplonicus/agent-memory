"""The hooks that keep the notes current: the Stop nudge, the decision reminder, the LOG guard and the
compaction mark. Driven with fake transcripts; the process tests run them the way Claude Code does."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_memory import handoff
from agent_memory.config import Config

SID = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
TAG = "s:0a1b2c3d"


def call(name, **tool_input):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


EDIT = call("Edit", file_path="/repo/src/app.py", old_string="a", new_string="b")
COMMIT = call("Bash", command='git add src/app.py && git commit -m "fix"')
READ_NOW = call("Bash", command="cat /repo/NOW.md && tail -5 /notes/LOG.md")
WRITE_NOW = call("Write", file_path="/repo/NOW.md", content="# NOW")
APPEND_LOG = call("Bash", command='echo "- line s:0a1b2c3d" >> /notes/LOG.md')


@pytest.fixture
def env(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "LOG.md").write_text("- 2026-03-01 · someone else · s:ffffffff\n", encoding="utf-8")
    cfg = Config(notes_dir=notes, claude_dir=tmp_path / "claude", project_dirs=[tmp_path], env_file=tmp_path / "no.env")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[paths]\nnotes_dir = "{notes.as_posix()}"\n', encoding="utf-8")

    def transcript(*entries):
        path = tmp_path / "t.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        return {"session_id": SID, "transcript_path": str(path), "cwd": "/repo", "hook_event_name": "Stop"}

    def run(name, event):
        return subprocess.run([sys.executable, "-m", "agent_memory", "hook", name], input=json.dumps(event),
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "AGENT_MEMORY_CONFIG": str(cfg_file)})

    return type("Env", (), {"cfg": cfg, "notes": notes, "transcript": staticmethod(transcript), "run": staticmethod(run)})


def reason(env, *entries):
    out = handoff.stop(env.cfg, env.transcript(*entries))
    return out and out["reason"]


# --- the Stop nudge ------------------------------------------------------------

def test_work_with_no_log_line_is_sent_back(env):
    r = reason(env, EDIT, EDIT, EDIT)
    assert r and TAG in r and "3 edit(s) and 0 commit(s)" in r and str(env.cfg.log_file) in r


def test_two_edits_are_below_the_bar(env):
    assert reason(env, EDIT, EDIT) is None


def test_a_session_that_only_read_things_is_left_alone(env):
    assert reason(env, READ_NOW, call("Read", file_path="/repo/a.py"), READ_NOW) is None


def test_reading_the_state_files_does_not_count_as_writing_them(env):
    assert handoff.classify("Bash", READ_NOW["message"]["content"][0]["input"]) is None
    work = handoff.work_summary(env.transcript(COMMIT, READ_NOW)["transcript_path"])
    assert work["since"] == {"edit": 0, "commit": 1} and work["wrote_state"] is False


def test_a_logged_session_with_nothing_new_since_passes(env):
    env.cfg.log_file.write_text(f"- did things · {TAG}\n", encoding="utf-8")
    assert reason(env, EDIT, EDIT, COMMIT, WRITE_NOW, APPEND_LOG) is None


def test_a_commit_after_the_last_state_write_is_sent_back_even_when_logged(env):
    env.cfg.log_file.write_text(f"- did things · {TAG}\n", encoding="utf-8")
    r = reason(env, EDIT, COMMIT, APPEND_LOG, EDIT, COMMIT)
    assert r and "committed 1 time(s) since" in r and "1 other edit(s)" in r


def test_edits_alone_after_logging_do_not_trip_it(env):
    env.cfg.log_file.write_text(f"- did things · {TAG}\n", encoding="utf-8")
    assert reason(env, EDIT, COMMIT, APPEND_LOG, EDIT, EDIT, EDIT, EDIT) is None


def test_someone_elses_tag_in_the_log_does_not_count(env):
    assert reason(env, COMMIT, COMMIT, COMMIT) is not None


def test_it_never_blocks_twice_in_a_row(env):
    event = env.transcript(EDIT, EDIT, EDIT)
    assert handoff.stop(env.cfg, event) is not None
    assert handoff.stop(env.cfg, dict(event, stop_hook_active=True)) is None


def test_subagent_work_and_broken_lines_are_ignored(env):
    side = dict(EDIT, isSidechain=True)
    event = env.transcript(side, side, side, {"type": "user", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {}}]}})
    with open(event["transcript_path"], "a", encoding="utf-8") as f:
        f.write('{"tool_use" broken\n')
    assert handoff.stop(env.cfg, event) is None


def test_a_refused_or_failed_call_changed_nothing(env):
    def attempt(i, entry):
        e = json.loads(json.dumps(entry)); e["message"]["content"][0]["id"] = f"t{i}"; return e
    refused = [attempt(i, c) for i, c in enumerate((COMMIT, EDIT, EDIT))]
    results = [{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "is_error": True,
                                                         "content": "permission denied"}]}} for i in range(3)]
    assert reason(env, *[x for pair in zip(refused, results) for x in pair]) is None
    ok = [{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}]}}
          for i in range(3)]
    assert reason(env, *[x for pair in zip(refused, ok) for x in pair]) is not None


def test_a_powershell_append_counts_as_logging(env):
    env.cfg.log_file.write_text(f"- did things · {TAG}\n", encoding="utf-8")
    ps_log = call("PowerShell", command='Add-Content C:\\notes\\LOG.md "- line s:0a1b2c3d"')
    assert reason(env, COMMIT, ps_log) is None


def test_stop_as_a_process_prints_a_block_or_nothing(env):
    out = env.run("stop", env.transcript(EDIT, EDIT, EDIT))
    assert out.returncode == 0 and json.loads(out.stdout)["decision"] == "block"
    out = env.run("stop", env.transcript(EDIT))
    assert out.returncode == 0 and out.stdout == ""


# --- the decision reminder -----------------------------------------------------

@pytest.mark.parametrize("text", [
    "leave the old screenshots as is",
    "don't squash the history",
    "the pin order is final",
    "actually i'll run the evals in the other session",
    "never touch the backup drive",
    "let's not ship that yet",
    "hold off on the deploy, waiting on Priya",
    "that session is writing evals but I will clear both when it's done",
    "i closed the editor, waiting for the other one",
])
def test_decisions_are_noticed(text):
    note = handoff.decision_note(text)
    assert note and "NOW.md" in note


@pytest.mark.parametrize("text", ["hello", "can you fix the overlap in the status bar", "what are they showing?",
                                  "run the tests", ""])
def test_plain_requests_are_not(text):
    assert handoff.decision_note(text) is None


def test_pasted_text_is_not_read_for_decisions():
    assert handoff.decision_note('look <pasted_content id="1">we decided never to ship</pasted_content id="1">') is None


def test_prompt_as_a_process(env):
    out = env.run("prompt", {"session_id": SID, "prompt": "leave it as is", "hook_event_name": "UserPromptSubmit"})
    extra = json.loads(out.stdout)["hookSpecificOutput"]
    assert extra["hookEventName"] == "UserPromptSubmit" and "may settle something" in extra["additionalContext"]
    out = env.run("prompt", {"session_id": SID, "prompt": "hi"})
    assert out.returncode == 0 and out.stdout == ""


# --- the LOG guard -------------------------------------------------------------

def test_a_whole_file_write_of_the_log_is_denied(env):
    out = handoff.pre_write(env.cfg, {"tool_name": "Write", "tool_input": {"file_path": str(env.cfg.log_file)}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_other_writes_and_edits_pass(env):
    assert handoff.pre_write(env.cfg, {"tool_name": "Write", "tool_input": {"file_path": str(env.notes / "NOW.md")}}) is None
    assert handoff.pre_write(env.cfg, {"tool_name": "Edit", "tool_input": {"file_path": str(env.cfg.log_file)}}) is None


# --- the compaction mark -------------------------------------------------------

def test_compaction_appends_one_tagged_line(env):
    out = env.run("pre-compact", {"session_id": SID, "cwd": "/home/x/dev/proj", "trigger": "auto", "transcript_path": "/t/abc.jsonl"})
    assert out.returncode == 0
    lines = env.cfg.log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and lines[0].endswith("s:ffffffff")
    assert lines[1].endswith(TAG) and "context compacted (auto)" in lines[1] and "/t/abc.jsonl" in lines[1]


def test_compaction_never_glues_onto_a_line_without_a_newline(env):
    env.cfg.log_file.write_text("- 2026-03-01 · last line · s:ffffffff", encoding="utf-8")
    handoff.pre_compact(env.cfg, {"session_id": SID, "cwd": "/repo", "trigger": "manual"})
    lines = env.cfg.log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and lines[0].endswith("s:ffffffff") and lines[1].endswith(TAG)


def test_a_broken_hook_fails_open(env):
    out = env.run("stop", {"session_id": SID, "transcript_path": 12345})
    assert out.returncode == 0 and out.stdout == ""


def test_the_compaction_line_does_not_count_as_logging(env):
    """pre-compact tags its line with the session's own tag; that line is the hook's, not the session's
    record, so a long session that compacted is still sent back for its own LOG line."""
    handoff.pre_compact(env.cfg, {"session_id": SID, "cwd": "/repo", "trigger": "auto", "transcript_path": "/t/x.jsonl"})
    assert TAG in env.cfg.log_file.read_text(encoding="utf-8")
    assert not handoff.logged(env.cfg, SID)
    r = reason(env, EDIT, EDIT, EDIT)
    assert r and "LOG.md has no line tagged" in r
    with env.cfg.log_file.open("a", encoding="utf-8") as f:
        f.write(f"- 2026-03-02 · Claude Code · repo · did things · {TAG}\n")
    assert handoff.logged(env.cfg, SID)


def test_the_audit_ignores_the_compaction_line(env, monkeypatch, tmp_path):
    from agent_memory import audit
    folder = env.cfg.claude_dir / "projects" / "-repo"
    folder.mkdir(parents=True)
    (folder / f"{SID}.jsonl").write_text("\n".join(json.dumps(EDIT, separators=(",", ":")) for _ in range(3)) + "\n",
                                         encoding="utf-8")
    marker = tmp_path / "installed"
    marker.touch()
    os.utime(marker, (1, 1))
    monkeypatch.setattr(audit, "INSTALLED", marker)
    handoff.pre_compact(env.cfg, {"session_id": SID, "cwd": "/repo", "trigger": "auto"})
    assert [t for _, t, _, _ in audit.unlogged(env.cfg)] == [TAG]
    with env.cfg.log_file.open("a", encoding="utf-8") as f:
        f.write(f"- 2026-03-02 · Claude Code · repo · did things · {TAG}\n")
    assert audit.unlogged(env.cfg) == []
