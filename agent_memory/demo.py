"""`agent-memory demo`: load the invented demo projects (examples/demo) into database "demo" and show
what a session sees. Your own files and your own database are not touched.

The demo is copied to $XDG_STATE_HOME/agent-memory/demo first, because Claude Code names memory folders
after the absolute path of the project, which depends on where that copy lives.
"""
from __future__ import annotations

import shutil
from dataclasses import replace

from .config import REPO, STATE_DIR, load
from .db import apply_schema, connect
from .embed import ollama, sync_embeddings
from .hook import session_start
from .importer import Importer
from .search import format_hit, search
from .sources import encode

SRC = REPO / "examples" / "demo"
DEST = STATE_DIR / "demo"
QUERIES = [
    ("What is waiting on whom, across every project", "RETURN fn::waiting_on()"),
    ("Claims nobody has verified", "RETURN fn::unverified()"),
    ("Past their review date (as of 2026-03-25)", "RETURN fn::overdue('2026-03-25')"),
    ("Memories that contradict each other", "RETURN fn::conflicts()"),
    ("Tidepool's decisions against", "RETURN fn::entries('tidepool', 'decided_against')"),
    ("Everything session s:e03d6c58 logged", "RETURN fn::session('s:e03d6c58')"),
]
QUESTION = "why don't we call the tide API when someone opens a chart"


def build() -> dict:
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(SRC, DEST, ignore=shutil.ignore_patterns("memory"))
    for proj in (SRC / "memory").iterdir():
        mem = DEST / "claude" / "projects" / f"{encode(DEST / 'projects')}-{proj.name}" / "memory"
        shutil.copytree(proj, mem)
    return {"claude_dir": DEST / "claude", "notes_dir": DEST / "notes", "project_dirs": [DEST / "projects"]}


def main(args: list[str]) -> None:
    cfg = replace(load(), db="demo", **build())
    errors = apply_schema(cfg)
    if errors:
        raise SystemExit("schema errors:\n  " + "\n  ".join(errors))
    conn = connect(cfg)
    conn.query("DELETE source; DELETE entry; DELETE log; DELETE emb; DELETE project; DELETE session; "
               "DELETE about; DELETE written_in; DELETE supersedes; DELETE contradicts;")
    print("sync", Importer(conn, cfg, log=lambda *a: None).sync())
    if cfg.embed:
        try:
            print("embed", sync_embeddings(conn, ollama(cfg), cfg.embed_model, log=lambda *a: None))
        except Exception as e:  # noqa: BLE001
            print(f"embed skipped ({type(e).__name__}); search below is keyword only")
    print("\n#### The brief a session started in projects/tidepool gets\n")
    print(session_start(cfg, {"session_id": "0123456789abcdef", "cwd": str(DEST / "projects" / "tidepool")}))
    for title, q in QUERIES:
        print(f"\n#### {title}\n$ agent-memory query \"{q}\"")
        rows = conn.query(q)
        for r in rows or ["(none)"]:
            keys = ("project", "review_by", "text") if "text" in r else r.keys() if isinstance(r, dict) else ()
            print(r if isinstance(r, str) else " · ".join(str(r[k]) for k in keys))
    print(f'\n#### Search by meaning\n$ agent-memory search "{QUESTION}" 3')
    hits, hybrid = search(conn, cfg, QUESTION, 3)
    for h in hits:
        line = format_hit(h, 160).replace(str(DEST) + "/", "")
        print(line.replace(encode(DEST / "projects"), "<project dir>"))
    print(f"\nDemo database: ns {cfg.ns}, db demo. Files: {DEST}")
