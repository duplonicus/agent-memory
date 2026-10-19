"""The sync daemon: keeps the SurrealDB mirror equal to the files (files -> SurrealDB, one way).

Polls the files (sha256 via the importer) every SYNC_EVERY seconds; inotify does not fire on every mount
(WSL's /mnt/c, network drives), polling does. A full pass every FULL_EVERY also runs the planner canary.
After a sync that changed something it brings the vectors level; Ollama being down is not a sync error:
the vectors wait (embed_error in the status file) and keyword search still works.

Status: $XDG_STATE_HOME/agent-memory/daemon.json.
"""
from __future__ import annotations

import json
import os
import signal
import time
import traceback
from datetime import datetime, timezone

from .canary import planner_mismatches
from .config import STATE_DIR, Config
from .db import connect
from .embed import ollama, sync_embeddings
from .importer import Importer

SYNC_EVERY = float(os.environ.get("AGENT_MEMORY_SYNC_EVERY", "20"))
FULL_EVERY = float(os.environ.get("AGENT_MEMORY_FULL_EVERY", "900"))
STATUS = STATE_DIR / "daemon.json"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def run(cfg: Config) -> None:
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    status = {"started": datetime.now(timezone.utc).isoformat(), "syncs": 0, "errors": 0, "last_error": None}
    last_full, embed_due = 0.0, True

    def write():
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = STATUS.with_suffix(".tmp")
            tmp.write_text(encoding="utf-8", data=json.dumps({**status, "updated": datetime.now(timezone.utc).isoformat()}, indent=1))
            tmp.replace(STATUS)
        except OSError:
            pass

    while not stop:
        try:
            conn = connect(cfg)
            stats = Importer(conn, cfg, log=log).sync()
            if time.time() - last_full > FULL_EVERY:
                last_full = time.time()
                bad = planner_mismatches(conn)
                status["planner_mismatches"] = len(bad)
                if bad:
                    log("WARN planner: an indexed + graph WHERE disagrees with NOINDEX; use the fn:: reads:", bad[:3])
            status["syncs"] += 1
            status["last_sync"] = datetime.now(timezone.utc).isoformat()
            status["last_sync_stats"] = stats
            if stats["files"] or stats["deleted"]:
                log("sync", stats)
                embed_due = True
            if embed_due and cfg.embed:
                try:
                    status["embed"] = sync_embeddings(conn, ollama(cfg), cfg.embed_model, log=log)
                    status["embed_error"] = None
                    embed_due = False
                except Exception as e:  # noqa: BLE001 - retried next pass
                    if status.get("embed_error") is None:
                        log("WARN embed:", type(e).__name__, e)
                    status["embed_error"] = f"{type(e).__name__}: {e}"
        except Exception as e:  # noqa: BLE001 - the daemon keeps running; the status file says what broke
            status["errors"] += 1
            status["last_error"] = f"{type(e).__name__}: {e}"
            log("ERROR", type(e).__name__, e)
            traceback.print_exc()
        write()
        for _ in range(int(SYNC_EVERY * 10)):
            if stop:
                break
            time.sleep(0.1)
    log("stopped")
