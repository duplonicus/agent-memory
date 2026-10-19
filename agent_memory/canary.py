"""Planner canary. SurrealDB 3.3.4's bitmap planner (indexes combined as bitmaps, new in 3.3.0) returned
wrong counts for an indexed field plus a graph condition in one WHERE: entry WHERE kind = 'decision'
AND ->about->project CONTAINS project:x gave 0 where the answer was 7 (2026-10-15). A minimal repro
did not show it, so this checks the live data instead: the same question asked both ways must agree."""
from __future__ import annotations

KINDS = ["decision", "open_thread", "state", "gotcha"]


def planner_mismatches(conn, projects: int = 8) -> list[dict]:
    top = conn.query("SELECT VALUE id FROM (SELECT id, count(<-about) AS n FROM project) ORDER BY n DESC LIMIT $n", {"n": projects}) or []
    out = []
    for pid in top:
        for kind in KINDS:
            v = {"p": pid, "k": kind}
            fast = conn.query("SELECT VALUE count() FROM entry WHERE kind = $k AND ->about->project CONTAINS $p GROUP ALL", v)
            safe = conn.query("SELECT VALUE count() FROM entry WITH NOINDEX WHERE kind = $k AND ->about->project CONTAINS $p GROUP ALL", v)
            fast, safe = (fast or [0])[0], (safe or [0])[0]
            if fast != safe:
                out.append({"project": str(pid), "kind": kind, "indexed": fast, "noindex": safe})
    return out
