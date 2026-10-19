"""Hybrid search: embed the question here, then fn::search fuses keyword and vector hits.
Falls back to keyword only (and says so on stderr) when Ollama does not answer."""
from __future__ import annotations

import sys

from .config import Config
from .embed import embed_query, ollama


def search(conn, cfg: Config, q: str, limit: int = 10) -> tuple[list[dict], bool]:
    if cfg.embed:
        try:
            qv = embed_query(q, ollama(cfg))
            return conn.query("RETURN fn::search($q, $n, $qv)", {"q": q, "n": limit, "qv": qv}), True
        except Exception as e:  # noqa: BLE001 - keyword is the fallback
            print(f"keyword only: Ollama did not embed the question ({type(e).__name__}: {e})", file=sys.stderr)
    return conn.query("RETURN fn::search($q, $n)", {"q": q, "n": limit}), False


def format_hit(h: dict, width: int = 220) -> str:
    text = " ".join(h["text"].split())
    return f"{h['project']} · {h['kind']} · {text[:width]}{'…' if len(text) > width else ''}  [{h['path']}:{h.get('line', '')}]"
