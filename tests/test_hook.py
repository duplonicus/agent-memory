"""The session-start brief, files only."""
import os
import subprocess
import time

from agent_memory.hook import session_start


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


def test_brief_has_session_tag_both_nows_and_log_tail(demo):
    out = session_start(demo, {"session_id": "0123456789abcdef", "cwd": str(demo.project_dirs[0] / "tidepool")})
    assert "LOG.md tag: s:01234567" in out
    assert f"=== {demo.notes_dir / 'NOW.md'}" in out
    assert f"=== {demo.project_dirs[0] / 'tidepool' / 'NOW.md'}" in out
    tail = out.split("=== last 5 of")[1].split("\n\n")[0].splitlines()[1:]
    assert tail == [l for l in (demo.notes_dir / "LOG.md").read_text(encoding="utf-8").splitlines() if l.startswith("- 2026-")][-5:]
    assert "STALE" not in out and "OVERSIZE" not in out


def test_overdue_threads_lead(demo):
    out = session_start(demo, {"cwd": str(demo.project_dirs[0] / "tidepool")})
    threads = out.split("## Open threads (waiting on whom)\n")[1].split("\n## ")[0].splitlines()
    assert threads[0].startswith("OVERDUE - Waiting on Priya")
    assert threads[1].startswith("OVERDUE - Waiting on Marco")


def test_stale_when_repo_has_newer_commits(demo):
    proj = demo.project_dirs[0] / "tidepool"
    _git(proj, "init", "-q")
    old = time.time() - 3600
    os.utime(proj / "NOW.md", (old, old))
    (proj / "x.txt").write_text("x", encoding="utf-8")
    _git(proj, "add", "x.txt")
    _git(proj, "commit", "-q", "--no-gpg-sign", "-m", "x")
    out = session_start(demo, {"cwd": str(proj)})
    assert out.startswith("=== warnings ===")
    assert "!!! STALE: 1 commit(s) in tidepool" in out


def test_repo_without_now_gets_a_hint(demo, tmp_path):
    repo = tmp_path / "other"
    repo.mkdir()
    _git(repo, "init", "-q")
    assert "No NOW.md for this repo" in session_start(demo, {"cwd": str(repo)})


def test_oversize_now_warns_and_stays_under_the_harness_cap(demo):
    now = demo.project_dirs[0] / "tidepool" / "NOW.md"
    now.write_bytes((now.read_text(encoding="utf-8") + "".join(f"- 2026-03-01, Sam: decision {i}. " + "Reason. " * 40 + "\n" for i in range(60))).encode())
    out = session_start(demo, {"cwd": str(now.parent)})
    assert "!!! OVERSIZE" in out and "clipped brief" in out
    assert len(out) < 10000


def test_a_worktree_gets_the_main_checkouts_now(demo, tmp_path):
    """NOW.md is untracked (.git/info/exclude), so a worktree has none; the brief reads the main checkout's."""
    proj = demo.project_dirs[0] / "tidepool"
    _git(proj, "init", "-q")
    (proj / "x.txt").write_text("x", encoding="utf-8")
    _git(proj, "add", "x.txt")
    _git(proj, "commit", "-q", "--no-gpg-sign", "-m", "x")
    wt = tmp_path / "wt"
    _git(proj, "worktree", "add", "-q", str(wt), "-b", "feat/x")
    out = session_start(demo, {"cwd": str(wt)})
    assert f"=== {proj / 'NOW.md'}" in out
    assert "No NOW.md for this repo" not in out
