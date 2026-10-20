"""agent-memory: the command line.

    agent-memory install            set everything up (see install.py; asks before each change outside the repo)
    agent-memory demo               load the invented demo projects into db "demo" and show a brief and a search
    agent-memory search "question" [n]
    agent-memory query "SurrealQL"  e.g. "RETURN fn::waiting_on()"
    agent-memory sync [--force]     one pass, files -> SurrealDB
    agent-memory daemon             the sync loop (the service runs this)
    agent-memory schema             apply schema.surql and functions.surql (idempotent)
    agent-memory hook [name]        a Claude Code hook, event JSON on stdin: session-start (the brief, default),
                                    stop, prompt, pre-write, pre-compact (agent_memory/handoff.py)
    agent-memory status             config paths, database and Ollama reachability, daemon status
"""
from __future__ import annotations

import json
import sys
import urllib.request

from . import __version__
from .config import CONFIG_DIR, Config, load


def _search(cfg: Config, args: list[str]) -> None:
    from .db import connect
    from .search import format_hit, search
    if not args:
        sys.exit('usage: agent-memory search "question" [n]')
    hits, _ = search(connect(cfg), cfg, args[0], int(args[1]) if len(args) > 1 else 10)
    for h in hits:
        print(format_hit(h))
    if not hits:
        print("no hits")


def _query(cfg: Config, args: list[str]) -> None:
    from .db import sql
    q = args[0] if args else sys.stdin.read()
    status = 0
    for r in sql(cfg, q):
        if r.get("status") != "OK":
            print("ERROR:", r.get("result"), file=sys.stderr)
            status = 1
            continue
        v = r["result"]
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            print("\n".join(v))
        else:
            print(json.dumps(v, ensure_ascii=False, indent=1))
    sys.exit(status)


def _sync(cfg: Config, args: list[str]) -> None:
    from .db import connect
    from .embed import ollama, sync_embeddings
    from .importer import Importer
    conn = connect(cfg)
    print("sync", Importer(conn, cfg).sync(force="--force" in args))
    if cfg.embed:
        try:
            print("embed", sync_embeddings(conn, ollama(cfg), cfg.embed_model, log=lambda *a: None))
        except Exception as e:  # noqa: BLE001
            print(f"embed skipped: Ollama did not answer ({type(e).__name__}: {e}); keyword search still works")


def _status(cfg: Config, args: list[str]) -> None:
    from .daemon import STATUS
    print(f"config:   {CONFIG_DIR / 'config.toml'}")
    print(f"claude:   {cfg.claude_dir}")
    print(f"notes:    {cfg.notes_dir}")
    print(f"projects: {', '.join(map(str, cfg.project_dirs))}")
    for name, url in (("surreal", f"{cfg.surreal_url}/health"), ("ollama", f"{cfg.embed_url}/api/version")):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                print(f"{name + ':':9} up ({url})")
        except Exception as e:  # noqa: BLE001
            print(f"{name + ':':9} DOWN ({url}: {type(e).__name__})")
    if STATUS.exists():
        s = json.loads(STATUS.read_text(encoding="utf-8"))
        print(f"daemon:   last sync {s.get('last_sync')}, errors {s.get('errors')}, "
              f"last error {s.get('last_error')}, embed error {s.get('embed_error')}")
        for path in (s.get("last_sync_stats") or {}).get("skipped") or []:
            print(f"skipped:  {path} (not UTF-8; save it as UTF-8 and the next pass picks it up)")
    else:
        print("daemon:   no status file (not running yet?)")


def main(argv: list[str] | None = None) -> None:
    # Windows pipes default to the ANSI code page, which cannot print the · and → in the brief.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    if argv[0] == "--version":
        print(__version__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "hook":
        from .hook import main as hook_main
        hook_main(args)
        return
    if cmd == "install":
        from .install import main as install_main
        install_main(args)
        return
    if cmd == "demo":
        from .demo import main as demo_main
        demo_main(args)
        return
    cfg = load()
    if cmd == "search":
        _search(cfg, args)
    elif cmd == "query":
        _query(cfg, args)
    elif cmd == "sync":
        _sync(cfg, args)
    elif cmd == "daemon":
        from .daemon import run
        run(cfg)
    elif cmd == "schema":
        from .db import apply_schema
        errors = apply_schema(cfg)
        print("schema applied" if not errors else "schema errors:\n  " + "\n  ".join(errors))
        sys.exit(1 if errors else 0)
    elif cmd == "status":
        _status(cfg, args)
    else:
        sys.exit(f"unknown command {cmd!r}; agent-memory --help")


if __name__ == "__main__":
    main()
