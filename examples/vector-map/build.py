"""Build a 3-d map of your memory: every note's embedding, squashed from 768 dimensions to 3 with UMAP, as one
self-contained HTML page (rotate, zoom, search words, click a dot for its 5 nearest notes). Optional.

    uv run --extra map python examples/vector-map/build.py memory-map.html [--hide PROJECT ...]

Reads the vectors the sync daemon already made, so nothing is embedded again. --hide keeps a project's dots
but replaces their text with "(text hidden)": the page carries up to 280 characters of every note, so hide
anything private before you share it.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from agent_memory.config import load
from agent_memory.db import connect
from agent_memory.projects import canonical, norm

HERE = Path(__file__).resolve().parent


def hide_key(raw: str, cfg) -> str:
    """The name --hide matches a dot's project on: its canonical name, or for a project in [projects] drop
    (which has none) the normalized name, so every spelling of a dropped project still matches."""
    return (canonical(raw, cfg) or [norm(raw)])[0]


def hidden(argv: list[str], cfg) -> set[str]:
    """The --hide projects as hide keys, so the folder name (My_Client), the LOG spelling (my-client) and an
    alias all hide the same project, dropped or not."""
    return {name for i, a in enumerate(argv) if i and argv[i - 1] == "--hide"
            for name in canonical(a, cfg) or [norm(a)]}


def hide_report(hide: set[str], found: set[str]) -> list[str]:
    """What --hide did, printed whenever it was given, so a --hide that matched nothing never goes silent."""
    lines = [f"text hidden for: {', '.join(sorted(hide & found)) or 'none'}"]
    if hide - found:
        lines.append(f"WARN: no notes in {', '.join(sorted(hide - found))}; check the spelling against these "
                     f"projects: {', '.join(sorted(found))}")
    return lines


def main(argv: list[str]) -> None:
    if not argv or argv[0].startswith("-"):
        sys.exit(__doc__)
    import numpy as np
    import umap

    cfg = load()
    out, hide = Path(argv[0]), hidden(argv, cfg)
    conn = connect(cfg)
    meta = {r["k"]: r for r in conn.query("SELECT record::id(id) AS k, project, kind, text FROM entry "
                                          "WHERE status = 'active' AND source.archived != true")}
    keys, vecs, start = [], [], 0
    while True:
        rows = conn.query(f"SELECT record::id(id) AS k, v FROM emb ORDER BY id LIMIT 500 START {start}")
        if not rows:
            break
        for r in rows:
            if r["k"] in meta:
                keys.append(r["k"])
                vecs.append(r["v"])
        start += 500
    if len(keys) < 20:
        sys.exit(f"only {len(keys)} embedded notes; run the sync daemon (or `agent-memory sync`) with Ollama up first")
    X = np.array(vecs, dtype=np.float32)
    Y = umap.UMAP(n_components=3, n_neighbors=min(15, len(keys) - 1), min_dist=0.1, metric="cosine",
                  random_state=7).fit_transform(X)
    Y = (Y - Y.mean(0)) / Y.std(0)
    for a in range(3):  # pin the far 1% to the edges so a few outliers don't squash the cloud
        lo, hi = np.percentile(Y[:, a], [1, 99])
        Y[:, a] = np.clip(Y[:, a], lo, hi)
    # 5 nearest neighbours in the full 768-d space (cosine), for the side panel
    Xn = X / np.linalg.norm(X, axis=1, keepdims=True)
    nn = []
    for i in range(0, len(Xn), 1000):
        s = Xn[i:i + 1000] @ Xn.T
        for row, ids in enumerate(np.argsort(-s, axis=1)[:, 1:6]):
            nn.append([[int(j), round(float(1 - s[row, j]), 3)] for j in ids])
    pts, found = [], set()
    for i, k in enumerate(keys):
        m = meta[k]
        project = (canonical(m["project"], cfg) or [m["project"]])[0]
        found.add(key := hide_key(m["project"], cfg))
        text = " ".join((m.get("text") or "").split())
        pts.append({"p": project, "k": m["kind"], "x": round(float(Y[i, 0]), 3), "y": round(float(Y[i, 1]), 3),
                    "z": round(float(Y[i, 2]), 3), "t": "(text hidden)" if key in hide else text[:280], "n": nn[i]})
    if "--hide" in argv[1:]:
        print("\n".join(hide_report(hide, found)))
    data = json.dumps(pts, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (HERE / "template.html").read_text(encoding="utf-8")
    out.write_text(html.replace("__DATA__", data).replace("__BUILT__", date.today().isoformat()), encoding="utf-8")
    print(f"wrote {out}: {len(pts)} notes, {len({p['p'] for p in pts})} projects")


if __name__ == "__main__":
    main(sys.argv[1:])
