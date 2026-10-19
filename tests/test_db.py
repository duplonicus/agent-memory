"""Through SurrealDB: import the demo, render it back byte for byte, edit, move and delete files, and read
it back through the fn:: API. Opt-in, because it creates and drops a database: set AGENT_MEMORY_TEST_ENV
to an .env with AGENT_MEMORY_ROOT_USER/PASS and AGENT_MEMORY_USER/PASS for a SurrealDB 3.3.4 at
AGENT_MEMORY_TEST_URL (default http://127.0.0.1:8000). Uses ns agent_memory_test."""
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from surrealdb import RecordID

from agent_memory.db import apply_schema, connect, sql
from agent_memory.importer import Importer, source_id
from agent_memory.parse import split_blocks

ENV = os.environ.get("AGENT_MEMORY_TEST_ENV")
pytestmark = pytest.mark.skipif(not ENV, reason="set AGENT_MEMORY_TEST_ENV to run the database tests")


@pytest.fixture
def db(demo):
    cfg = replace(demo, surreal_url=os.environ.get("AGENT_MEMORY_TEST_URL", "http://127.0.0.1:8000"),
                  ns="agent_memory_test", db="t", env_file=Path(ENV))
    sql(cfg, "REMOVE DATABASE IF EXISTS t;", root=True)
    assert apply_schema(cfg) == []
    conn = connect(cfg)
    yield cfg, conn, Importer(conn, cfg, log=lambda *a: None)
    sql(cfg, "REMOVE NAMESPACE IF EXISTS agent_memory_test;", root=True)


def render(conn, path):
    sid = source_id(conn.query("SELECT VALUE locator FROM ONLY source WHERE path = $p LIMIT 1", {"p": str(path)}))
    rows = conn.query("SELECT ord, raw FROM entry WHERE source = $s AND status = 'active'", {"s": sid})
    rows += conn.query("SELECT ord, raw FROM log WHERE source = $s AND status = 'active'", {"s": sid})
    return "".join(r["raw"] for r in sorted(rows, key=lambda r: r["ord"]))


def test_every_file_renders_back_byte_for_byte(db):
    cfg, conn, imp = db
    stats = imp.sync()
    paths = conn.query("SELECT VALUE path FROM source WHERE status = 'active'")
    assert stats["files"] == len(paths) == 13
    for p in paths:
        assert render(conn, p) == Path(p).read_bytes().decode(), p
    assert imp.sync()["unchanged"] == 13


def test_reads(db):
    cfg, conn, imp = db
    imp.sync()
    # The global NOW.md's "## Open to-do" counts as open threads too.
    assert conn.query("RETURN fn::waiting_on('priya')") == [
        "global · **Tidepool** → `tidepool/NOW.md`: the tide-chart app; waiting on Priya for the new palette.",
        "tidepool · Waiting on Priya: the colour-blind-safe palette for the tide bands. (review by 2026-03-20)"]
    assert conn.query("RETURN fn::unverified()") == [
        "tidepool · Claimed, not verified: the harmonic math matches NOAA within 3 cm for all 40 stations (checked 6 of them)."]
    overdue = conn.query("RETURN fn::overdue('2026-03-25')")
    assert [(r["project"], r["review_by"]) for r in overdue] == [("tidepool", "2026-03-20"), ("garden-sensors", "2026-03-21")]
    later = conn.query("RETURN fn::overdue('2026-04-13')")
    assert ("garden-sensors", "2026-04-13") in [(r["project"], r["review_by"]) for r in later]  # memory frontmatter
    assert conn.query("RETURN fn::entries('tidepool', 'decided_against')") == [
        "2026-03-10, Sam: decided against a native mobile app; the PWA covers offline charts."]
    assert conn.query("RETURN fn::session('s:e03d6c58')") == [
        "- 2026-03-11 · Claude Code · tidepool + garden-sensors · shared the MQTT broker config between both projects · s:e03d6c58\n"]
    # A LOG line naming two projects belongs to both.
    assert any("s:e03d6c58" in l for l in conn.query("RETURN fn::logs('garden-sensors')"))
    assert conn.query("RETURN fn::conflicts()") == [
        {"memory": "probe-sleep", "contradicts": "always-on-gateway-probe", "project": "garden-sensors"}]
    hist = conn.query("RETURN fn::history('noaa-cache-ttl')")
    assert hist[0]["replaced_by"] == "no-noaa-at-view-time"


def test_search_leaves_out_superseded_and_archived(db):
    cfg, conn, imp = db
    (cfg.notes_dir / "archive").mkdir()
    (cfg.notes_dir / "archive" / "old.md").write_text("# Old\n\nNOAA cache everything forever.\n", encoding="utf-8")
    imp.sync()
    hits = conn.query("RETURN fn::search('NOAA cache', 20)")
    paths = {Path(h["path"]).name for h in hits}
    assert hits and "noaa-cache-ttl.md" not in paths and "old.md" not in paths
    # without the supersedes line, the old memory is searchable again
    new = next(Path(p) for p in conn.query("SELECT VALUE path FROM source") if p.endswith("no-noaa-at-view-time.md"))
    new.write_bytes(new.read_bytes().replace(b"supersedes: noaa-cache-ttl\n", b""))
    imp.sync()
    assert "noaa-cache-ttl.md" in {Path(h["path"]).name for h in conn.query("RETURN fn::search('NOAA cache', 20)")}


def test_edit_supersedes_changed_blocks_only(db):
    cfg, conn, imp = db
    imp.sync()
    now = cfg.project_dirs[0] / "tidepool" / "NOW.md"
    before = set(map(str, conn.query("SELECT VALUE id FROM entry WHERE path = $p AND status = 'active'", {"p": str(now)})))
    now.write_bytes(now.read_bytes().replace(b"Tests: 212 passing", b"Tests: 230 passing"))
    stats = imp.sync()
    assert stats["files"] == 1 and stats["superseded"] == 1
    after = set(map(str, conn.query("SELECT VALUE id FROM entry WHERE path = $p AND status = 'active'", {"p": str(now)})))
    assert len(before - after) == 1 and len(after - before) == 1
    assert render(conn, now) == now.read_bytes().decode()
    old = conn.query("SELECT text, status FROM entry WHERE text CONTAINS '212 passing'")
    assert old == [{"text": "Tests: 212 passing at commit 4e1d0aa.", "status": "superseded"}]


def test_a_moved_project_keeps_its_ids(db):
    cfg, conn, imp = db
    imp.sync()
    ids = set(map(str, conn.query("SELECT VALUE id FROM entry WHERE project = 'garden-sensors' AND status = 'active'")))
    root = cfg.project_dirs[0]
    shutil.move(root / "garden-sensors", root / "garden")
    stats = imp.sync()
    assert stats["moved"] == 1 and stats["deleted"] == 0
    moved = conn.query("SELECT VALUE path FROM source WHERE project = 'garden-sensors' AND kind = 'now'")
    assert moved == [str(root / "garden" / "NOW.md")]
    assert set(map(str, conn.query("SELECT VALUE id FROM entry WHERE project = 'garden-sensors' AND status = 'active'"))) == ids


def test_mass_delete_is_refused(db):
    cfg, conn, imp = db
    imp = Importer(conn, replace(cfg, max_deletes=5), log=lambda *a: None)
    imp.sync()
    shutil.rmtree(cfg.claude_dir / "projects")
    shutil.rmtree(cfg.project_dirs[0])
    stats = imp.sync()
    # 10 of 13 files gone at once (the project folder and the memory folders): refused, nothing retired
    assert stats["guarded"] == 10 and stats["deleted"] == 0
    assert len(conn.query("SELECT VALUE id FROM source WHERE status = 'active'")) == 13
    assert imp.sync(force=True)["deleted"] == 10


def test_planner_canary_runs(db):
    from agent_memory.canary import planner_mismatches
    cfg, conn, imp = db
    imp.sync()
    assert planner_mismatches(conn) == []


def test_an_unchanged_file_still_picks_up_a_new_archive_rule(db):
    cfg, conn, imp = db
    imp.sync()
    now = str(cfg.project_dirs[0] / "tidepool" / "NOW.md")
    conn.query("UPDATE source SET archived = true WHERE path = $p", {"p": now})
    assert imp.sync()["files"] == 1
    assert conn.query("SELECT VALUE archived FROM source WHERE path = $p", {"p": now}) == [False]
