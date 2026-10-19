"""Sessions that changed things but left no line in LOG.md.

LOG lines end with a session tag (s:<first 8 characters of the session id>). A session whose transcript
shows file edits or commits, and whose tag appears nowhere in LOG.md, did work the shared record does not
know about. The session-start brief lists those, so the gap shows up at the next start instead of never.
Only sessions after `agent-memory install` count: older ones never had a reason to log.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

from .config import STATE_DIR, Config

WORK = re.compile(r'"name":\s*"(Edit|Write|NotebookEdit)"|git commit|git push')
INSTALLED = STATE_DIR / "installed"


def unlogged(cfg: Config, days: int = 7, skip: str = "", min_actions: int = 3) -> list[tuple[str, str, str, int]]:
    """(last active, s:id8, project folder, edit/commit count) for each unlogged session, oldest first."""
    log = cfg.log_file
    logged = set(re.findall(r"s:([0-9a-f]{8})", log.read_text(encoding="utf-8", errors="replace"))) if log.exists() else set()
    began = INSTALLED.stat().st_mtime if INSTALLED.exists() else time.time()
    cutoff = max(time.time() - days * 86400, began)
    out = []
    for path in (cfg.claude_dir / "projects").glob("*/*.jsonl"):
        sid = path.stem
        if sid == skip or sid[:8] in logged or path.stat().st_mtime < cutoff:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Count only the session's own actions, not transcripts it pasted or discussed.
        hits = sum(1 for line in text.splitlines() if '"type":"assistant"' in line and WORK.search(line))
        if hits >= min_actions:
            when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            out.append((when, "s:" + sid[:8], path.parent.name, hits))
    return sorted(out)
