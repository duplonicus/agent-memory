"""Files -> SurrealDB rows, one way. Deterministic and lossless: ids are content-addressed, so a re-import
of an unchanged file is a no-op and an edited file only touches the blocks that changed. Blocks that
vanish from a file are not deleted but marked superseded, so the database keeps the history.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from surrealdb import RecordID

from .config import Config
from .parse import Block, split_blocks, sections
from .projects import canonical
from .sources import Source, enumerate_sources

# - 2026-10-18 · Claude Code · my-app · what happened · s:1a2b3c4d
LOG_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · ([^·]+?) · ([^·]+?) · (.*?)(?: · (s:[A-Za-z0-9_-]+))?[ \t]*$")
# A capital NOT counts ("NOT doing X"); a lowercase "not" inside a sentence does not ("X, not Y").
AGAINST = re.compile(r"(?i:decided against|declined|decided not|not to |won'?t |no longer|parked|dropped|rejected)|\bNOT\b")
NOW_SECTIONS = [("state", "state"), ("where", "where"), ("next", "next"), ("decision", "decision"),
                ("open", "open_thread"), ("gotcha", "gotcha")]
REVIEW_BY = re.compile(r"\(review by (\d{4}-\d{2}-\d{2})\)", re.I)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BATCH = 400


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _h(*parts: str) -> str:
    return hashlib.sha1("\0".join(parts).encode("utf-8", "surrogatepass")).hexdigest()[:24]


def source_id(key: str) -> RecordID:
    return RecordID("source", "s" + _h(key))


def _names(value: str | None) -> list[str]:
    """`supersedes: a, b` or `supersedes: [a, b]` -> ["a", "b"]."""
    if not value:
        return []
    return [n.strip().strip("\"'") for n in value.strip("[]").split(",") if n.strip().strip("\"'")]


def now_kind(block: Block) -> str:
    """A NOW.md block's kind comes from its H2 section (section[1]; section[0] is the H1 title)."""
    if len(block.section) < 2:
        return "preamble"
    top = block.section[1].lower()
    for prefix, kind in NOW_SECTIONS:
        if top.startswith(prefix):
            if kind == "decision" and AGAINST.search(block.text):
                return "decided_against"
            return kind
    return "note"


def block_kind(src: Source, block: Block, mem_type: str | None) -> str:
    if block.block in ("heading", "frontmatter", "code", "table", "blank"):
        return block.block
    if src.kind == "rules":
        return "rule"
    if src.kind == "project_claude":
        return "project_rule"
    if src.kind == "now":
        return now_kind(block)
    if src.kind == "memory":
        return "memory_" + (mem_type if mem_type in ("user", "feedback", "project", "reference") else "project")
    if src.kind == "memory_index":
        return "memory_index"
    if src.kind == "log":
        return "preamble"
    return "doc_section"


def rows_for(src: Source, content: str, now: datetime) -> tuple[dict, list[dict], list[dict]]:
    """(source row, entry rows, log rows) for one file."""
    sid = source_id(src.key)
    blocks = split_blocks(content)
    front = next((b for b in blocks if b.block == "frontmatter"), None)
    f = front.fields if front else {}
    mem_type = (f.get("type") or f.get("metadata.type") or "").strip() or None
    fm_review = (f.get("review_by") or f.get("metadata.review_by") or "").strip()
    fm_review = fm_review if DATE.match(fm_review) else None
    entries: list[dict] = []
    logs: list[dict] = []
    seen: dict[str, int] = {}

    def eid(section: list[str], text: str) -> RecordID:
        key = "\0".join([src.key, "/".join(section), text])
        n = seen.get(key, 0)
        seen[key] = n + 1
        return RecordID("entry", "e" + _h(key, str(n)))

    def entry(ord_: int, b: Block, kind: str, block: str, text: str, raw: str, review_by: str | None) -> dict:
        why = text[len("**Why:**"):].strip() if text.startswith("**Why:**") else None
        how = text[len("**How to apply:**"):].strip() if text.startswith("**How to apply:**") else None
        return {"id": eid(b.section, text), "source": sid, "path": src.path, "project": src.project,
                "ord": float(ord_), "line": b.line, "kind": kind, "block": block, "level": b.level,
                "depth": b.depth if block != "section" else None, "section": b.section, "text": text, "raw": raw,
                "why": why, "how_to_apply": how, "status": "active", "valid_from": now, "valid_to": None,
                "recorded_at": now, "review_by": review_by}

    if src.kind == "doc":
        for ord_, group in enumerate(sections(blocks)):
            text = "\n".join(b.text for b in group if b.text).strip()
            m = REVIEW_BY.search(text)
            entries.append(entry(ord_, group[0], "doc_section", "section", text, "".join(b.raw for b in group),
                                 m and m.group(1)))
    else:
        for ord_, b in enumerate(blocks):
            m = LOG_LINE.match(b.raw.rstrip("\r\n")) if src.kind == "log" and b.block == "item" else None
            if m and b.raw.count("\n") <= 2:
                day, surface, project, summary, tag = m.groups()
                n = seen.setdefault("log:" + b.raw, 0)
                seen["log:" + b.raw] = n + 1
                logs.append({"id": RecordID("log", "l" + _h(src.key, b.raw.rstrip("\r\n"), str(n))),
                             "source": sid, "ord": float(ord_), "line": b.line, "day": day,
                             "surface": surface.strip(), "project": project.strip(), "summary": summary.strip(),
                             "tag": tag, "raw": b.raw, "status": "active", "recorded_at": now})
                continue
            m = REVIEW_BY.search(b.text)
            review = m.group(1) if m else (fm_review if b.block == "frontmatter" else None)
            entries.append(entry(ord_, b, block_kind(src, b, mem_type), b.block, b.text, b.raw, review))
    source_row = {
        "id": sid, "path": src.path, "locator": src.key, "kind": src.kind, "project": src.project,
        "bytes": len(content.encode("utf-8")), "sha256": sha256(content.encode("utf-8")),
        "mtime": datetime.fromtimestamp(Path(src.path).stat().st_mtime, tz=timezone.utc),
        "imported_at": now, "archived": src.archived, "name": f.get("name"), "description": f.get("description"),
        "mem_type": mem_type, "status": "active",
        "supersedes": _names(f.get("supersedes") or f.get("metadata.supersedes")),
        "contradicts": _names(f.get("contradicts") or f.get("metadata.contradicts")),
        "review_by": fm_review,
    }
    return source_row, entries, logs


class Importer:
    def __init__(self, conn, cfg: Config, log=print):
        self.conn = conn
        self.cfg = cfg
        self.log = log

    def q(self, sql: str, vars: dict | None = None):
        return self.conn.query(sql, vars or {})

    def existing(self) -> dict[str, dict]:
        """Active sources by id. Keyed by id, not path, so a file that moved (same id, new path) is
        recognised as the same source."""
        rows = self.q("SELECT record::id(id) AS sid, path, sha256, locator, project, archived FROM source "
                      "WHERE status = 'active'") or []
        return {r["sid"]: r for r in rows}

    def _resolve(self, sources: list[Source], have: dict[str, dict], stats: dict) -> tuple[list[Source], dict]:
        """Give each source the key it already has in the database, then match moves.

        A source new to the database whose bytes equal exactly one source that vanished in this pass IS
        that source, moved: it takes over its locator and project, so its ids, vectors and edges carry
        on. Ambiguous matches (two files with the same bytes) and moved-and-edited files fall back to
        delete + new, history kept. Returns the resolved sources and the sources that are really gone."""
        by_path = {v["path"]: v for v in have.values()}
        out = []
        for src in sources:
            known = by_path.get(src.path)
            if known and known.get("locator"):
                src = replace(src, locator=known["locator"], project=known["project"])
            out.append(src)
        sids = {source_id(s.key).id for s in out}
        gone = {sid: v for sid, v in have.items() if sid not in sids}
        new = [i for i, s in enumerate(out) if source_id(s.key).id not in have]
        gone_by_sha: dict[str, list[str]] = {}
        for sid, v in gone.items():
            gone_by_sha.setdefault(v["sha256"], []).append(sid)
        new_by_sha: dict[str, list[int]] = {}
        for i in new:
            new_by_sha.setdefault(sha256(Path(out[i].path).read_bytes()), []).append(i)
        for sha, idx in new_by_sha.items():
            olds = gone_by_sha.get(sha, [])
            if len(idx) == 1 and len(olds) == 1:
                v = gone.pop(olds[0])
                out[idx[0]] = replace(out[idx[0]], locator=v["locator"], project=v["project"])
                self.log(f"moved: {v['path']} -> {out[idx[0]].path}")
                stats["moved"] += 1
        return out, gone

    def sync(self, sources: list[Source] | None = None, force: bool = False) -> dict:
        sources = sources if sources is not None else enumerate_sources(self.cfg)
        have = self.existing()
        now = datetime.now(timezone.utc)
        stats = {"files": 0, "unchanged": 0, "entries": 0, "logs": 0, "superseded": 0, "deleted": 0, "moved": 0}
        sources, gone = self._resolve(sources, have, stats)
        for src in sources:
            sid = source_id(src.key).id
            data = Path(src.path).read_bytes()
            h = have.get(sid)
            # A changed archive rule must reach unchanged files too, so `archived` is part of "unchanged".
            if (not force and h and h["path"] == src.path and h["sha256"] == sha256(data)
                    and bool(h.get("archived")) == src.archived):
                stats["unchanged"] += 1
                continue
            stats["files"] += 1
            self._upsert(*rows_for(src, data.decode("utf-8"), now), now, stats)
        limit = max(self.cfg.max_deletes, len(have) // 5)
        if len(gone) > limit and not force:
            # A folder that vanished (an unmounted drive, a renamed project dir with stale config) would
            # otherwise retire hundreds of sources in one pass. Refuse; a real mass delete runs with force.
            self.log(f"WARN: {len(gone)} sources would be deleted (limit {limit}); refused. "
                     f"Check paths in the config, or run `agent-memory sync --force`.")
            stats["guarded"] = len(gone)
            return stats
        for sid in gone:
            self.q("UPDATE $sid SET status = 'deleted'; "
                   "UPDATE entry SET status = 'superseded', valid_to = $now WHERE source = $sid AND status = 'active'; "
                   "UPDATE log SET status = 'superseded' WHERE source = $sid AND status = 'active';",
                   {"sid": RecordID("source", sid), "now": now})
            stats["deleted"] += 1
        if stats["files"] or stats["deleted"] or force:
            self.link_memories()
        return stats

    def _upsert(self, source_row, entries, logs, now, stats):
        sid = source_row["id"]
        source_row = {**source_row, "projects": canonical(source_row["project"], self.cfg)}
        self.q("UPSERT $id CONTENT $row", {"id": sid, "row": source_row})
        keep = [e["id"] for e in entries] + [l["id"] for l in logs]
        r1 = self.q("UPDATE entry SET status = 'superseded', valid_to = $now WHERE source = $sid AND status = 'active' "
                    "AND id NOTINSIDE $keep RETURN id", {"sid": sid, "now": now, "keep": keep})
        r2 = self.q("UPDATE log SET status = 'superseded' WHERE source = $sid AND status = 'active' "
                    "AND id NOTINSIDE $keep RETURN id", {"sid": sid, "keep": keep})
        stats["superseded"] += len(r1 or []) + len(r2 or [])
        for i in range(0, len(entries), BATCH):
            self.q("INSERT INTO entry $rows ON DUPLICATE KEY UPDATE path = $input.path, project = $input.project, "
                   "source = $input.source, ord = $input.ord, line = $input.line, kind = $input.kind, "
                   "block = $input.block, level = $input.level, depth = $input.depth, section = $input.section, "
                   "raw = $input.raw, why = $input.why, how_to_apply = $input.how_to_apply, "
                   "review_by = $input.review_by, status = 'active', valid_to = NONE",
                   {"rows": entries[i:i + BATCH]})
        for i in range(0, len(logs), BATCH):
            self.q("INSERT INTO log $rows ON DUPLICATE KEY UPDATE source = $input.source, project = $input.project, "
                   "ord = $input.ord, line = $input.line, raw = $input.raw, status = 'active'",
                   {"rows": logs[i:i + BATCH]})
        stats["entries"] += len(entries)
        stats["logs"] += len(logs)
        # Graph: entry -about-> project, log -about-> project, log -written_in-> session.
        pids = [RecordID("project", n) for n in source_row["projects"]]
        for pid in pids:
            row = {"name": pid.id}
            if source_row["kind"] == "now":
                row["now_path"] = source_row["path"]
            self.q("UPSERT $pid MERGE $row", {"pid": pid, "row": row})
        ab = [{"id": RecordID("about", "a" + _h(str(e["id"]), str(pid))), "in": e["id"], "out": pid}
              for e in entries for pid in pids]
        for i in range(0, len(ab), BATCH):
            self.q("INSERT RELATION IGNORE INTO about $rows", {"rows": ab[i:i + BATCH]})
        if logs:
            tags = sorted({l["tag"] for l in logs if l["tag"]})
            self.q("INSERT IGNORE INTO session $rows", {"rows": [{"id": RecordID("session", t), "tag": t} for t in tags]})
            canon = {str(l["id"]): canonical(l["project"], self.cfg) for l in logs}
            names = sorted({p for ps in canon.values() for p in ps})
            self.q("INSERT IGNORE INTO project $rows", {"rows": [{"id": RecordID("project", p), "name": p} for p in names]})
            wi = [{"id": RecordID("written_in", "w" + _h(str(l["id"]), l["tag"])), "in": l["id"],
                   "out": RecordID("session", l["tag"])} for l in logs if l["tag"]]
            lab = [{"id": RecordID("about", "a" + _h(str(l["id"]), p)), "in": l["id"], "out": RecordID("project", p)}
                   for l in logs for p in canon[str(l["id"])]]
            for table, rows in (("written_in", wi), ("about", lab)):
                for i in range(0, len(rows), BATCH):
                    self.q(f"INSERT RELATION IGNORE INTO {table} $rows", {"rows": rows[i:i + BATCH]})

    def link_memories(self):
        """Memory frontmatter `supersedes:` and `contradicts:` name other memories. Rebuilt whole each
        time something changed: names resolve within the same project first, then anywhere. A superseded
        memory stays in the database (fn::history) but drops out of search."""
        mems = self.q("SELECT id, name, project, supersedes, contradicts FROM source "
                      "WHERE status = 'active' AND kind = 'memory' AND name != NONE") or []
        by_name: dict[str, list[dict]] = {}
        for m in mems:
            by_name.setdefault(m["name"], []).append(m)

        def find(name: str, project: str):
            cands = by_name.get(name, [])
            same = [c for c in cands if c["project"] == project]
            return (same or cands or [None])[0]

        self.q("DELETE supersedes; DELETE contradicts; UPDATE source SET superseded_by = NONE WHERE superseded_by != NONE;")
        for m in mems:
            for table in ("supersedes", "contradicts"):
                for name in m.get(table) or []:
                    t = find(name, m["project"])
                    if t is None or t["id"] == m["id"]:
                        continue
                    self.q(f"RELATE $a->{table}->$b", {"a": m["id"], "b": t["id"]})
                    if table == "supersedes":
                        self.q("UPDATE $b SET superseded_by = $a", {"a": m["id"], "b": t["id"]})
