"""Embeddings for fn::search's hybrid half: one emb row per active entry, from Ollama.

Ollama runs the model on your GPU when it finds one (NVIDIA CUDA, AMD ROCm, Apple Metal, Vulkan) and on
the CPU otherwise; nothing here changes for either. Entry ids are content-addressed, so the set of keys
is the whole state: embed the active keys emb lacks, delete the emb keys whose entry is gone. The prompt
formats are embeddinggemma's model card.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable

from surrealdb import RecordID

from .config import Config

DIM = 768
DOC = "title: none | text: {}"
QUERY = "task: search result | query: {}"
MAX_CHARS = 6000
BATCH = 32         # texts per Ollama call
INSERT = 20        # rows per insert; 200 x 768 floats went over the HTTP body limit

Embedder = Callable[[list[str]], list[list[float]]]


def ollama(cfg: Config) -> Embedder:
    def embed(texts: list[str], timeout: float = 300) -> list[list[float]]:
        body = json.dumps({"model": cfg.embed_model, "input": texts}).encode()
        req = urllib.request.Request(f"{cfg.embed_url}/api/embed", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["embeddings"]
    return embed


def embed_query(q: str, embedder: Embedder) -> list[float]:
    return embedder([QUERY.format(q)])[0]


def sync_embeddings(conn, embedder: Embedder, model: str, log=print) -> dict:
    # Archived files stay readable but get no vector: they would compete with the live file in search.
    want = set(conn.query("SELECT VALUE record::id(id) FROM entry WHERE status = 'active' AND text != '' "
                          "AND source.archived != true"))
    have = set(conn.query("SELECT VALUE record::id(id) FROM emb"))
    stale = sorted(have - want)
    if stale:
        conn.query("DELETE $ids", {"ids": [RecordID("emb", k) for k in stale]})
    missing = sorted(want - have)
    done = 0
    for i in range(0, len(missing), BATCH):
        keys = missing[i:i + BATCH]
        rows = conn.query("SELECT record::id(id) AS k, text FROM $ids", {"ids": [RecordID("entry", k) for k in keys]})
        vecs = embedder([DOC.format(r["text"][:MAX_CHARS]) for r in rows])
        if any(len(v) != DIM for v in vecs):
            raise ValueError(f"{model} returned a vector that is not {DIM}-dim; change DIMENSION in schema.surql")
        for j in range(0, len(rows), INSERT):
            conn.query("INSERT INTO emb $rows", {"rows": [{"id": RecordID("emb", r["k"]), "v": v, "model": model}
                                                          for r, v in zip(rows[j:j + INSERT], vecs[j:j + INSERT])]})
        done += len(rows)
    stats = {"embedded": done, "removed": len(stale), "total": len(want)}
    if done or stale:
        log("embed", stats)
    return stats
