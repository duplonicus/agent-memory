"""Time search: question embedding, hybrid fn::search, keyword fn::search. Prints p50/p95 per step and the
setup it ran on, as JSON, so a published number can carry its denominator, conditions and date.

    .venv/bin/python scripts/bench_search.py questions.txt [--reps 5]

questions.txt: one question per line. Uses the config's SurrealDB and Ollama (agent-memory status shows them).
One warm-up pass is run first and not counted.
"""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def bench(conn, embed, questions: list[str], reps: int = 5, limit: int = 10) -> dict:
    t: dict[str, list[float]] = {"embed": [], "hybrid": [], "keyword": [], "hybrid_total": []}
    for q in questions:  # warm-up
        conn.query("RETURN fn::search($q, $n, $qv)", {"q": q, "n": limit, "qv": embed(q)})
    for _ in range(reps):
        for q in questions:
            a = time.perf_counter(); qv = embed(q); b = time.perf_counter()
            conn.query("RETURN fn::search($q, $n, $qv)", {"q": q, "n": limit, "qv": qv}); c = time.perf_counter()
            conn.query("RETURN fn::search($q, $n)", {"q": q, "n": limit}); d = time.perf_counter()
            t["embed"].append(b - a); t["hybrid"].append(c - b); t["keyword"].append(d - c); t["hybrid_total"].append(c - a)
    return {k: {"p50_ms": round(statistics.median(v) * 1000, 1), "p95_ms": round(pct(v, 95) * 1000, 1), "n": len(v)}
            for k, v in t.items()}


def main() -> None:
    from agent_memory.config import load
    from agent_memory.db import connect
    from agent_memory.embed import embed_query, ollama
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    reps = int(args[args.index("--reps") + 1]) if "--reps" in args else 5
    questions = [l.strip() for l in open(args[0], encoding="utf-8") if l.strip()]
    cfg = load()
    conn = connect(cfg)
    emb = ollama(cfg)
    entries = conn.query("RETURN count(SELECT id FROM entry WHERE status = 'active')")
    print(json.dumps({"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "questions": len(questions),
                      "reps": reps, "limit": 10, "active_entries": entries, "model": cfg.embed_model,
                      "machine": platform.platform(), "results": bench(conn, lambda q: embed_query(q, emb), questions, reps)},
                     indent=1))


if __name__ == "__main__":
    main()
