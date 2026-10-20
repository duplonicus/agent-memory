"""Which files are memory and whose they are."""
from pathlib import Path

from agent_memory.config import Config
from agent_memory.importer import AGAINST, now_kind
from agent_memory.parse import split_blocks
from agent_memory.projects import canonical
from agent_memory.sources import archived, encode, enumerate_sources, memory_project


def test_encode_matches_claude_code_folder_names():
    assert encode("/home/sam/dev/my_app") == "-home-sam-dev-my-app"
    assert encode("/mnt/c/Users/sam/dev.win") == "-mnt-c-Users-sam-dev-win"
    assert encode("C:\\Users\\sam\\dev") == "C--Users-sam-dev"


def test_memory_project_strips_the_longest_project_dir():
    cfg = Config(project_dirs=[Path("/home/sam/dev"), Path("/home/sam/dev/work")])
    assert memory_project("-home-sam-dev-tidepool", cfg) == "tidepool"
    assert memory_project("-home-sam-dev-work-api", cfg) == "api"
    assert memory_project(encode(Path.home()), cfg) == "home"
    assert memory_project("-srv-elsewhere", cfg) == "srv-elsewhere"



def test_enumerate_demo(demo):
    got = {(Path(s.path).name, s.kind, s.project) for s in enumerate_sources(demo)}
    assert got == {
        ("CLAUDE.md", "rules", "global"),
        ("NOW.md", "now", "global"), ("LOG.md", "log", "global"),
        ("NOW.md", "now", "tidepool"), ("harmonics.md", "doc", "tidepool"), ("CLAUDE.md", "project_claude", "tidepool"),
        ("NOW.md", "now", "garden-sensors"),
        ("MEMORY.md", "memory_index", "tidepool"), ("no-noaa-at-view-time.md", "memory", "tidepool"),
        ("noaa-cache-ttl.md", "memory", "tidepool"),
        ("MEMORY.md", "memory_index", "garden-sensors"), ("probe-sleep.md", "memory", "garden-sensors"),
        ("always-on-gateway-probe.md", "memory", "garden-sensors"),
    }


def test_a_folder_without_now_md_is_not_a_project(demo):
    (demo.project_dirs[0] / "scratch").mkdir()
    (demo.project_dirs[0] / "scratch" / "notes.md").write_text("# x\n", encoding="utf-8")
    assert not [s for s in enumerate_sources(demo) if s.project == "scratch"]


def test_archived():
    assert archived("archive/NOW.md") and archived("NOW-archive-2026-01-01.md")
    assert not archived("backup-plan.md") and not archived("NOW.md")
    # Only the dated-copy convention counts; a name that merely mentions archiving is a live note.
    assert archived("NOW-archive-2026-10-15.md") and archived("notes-archive-2026-10-15-b.md")
    assert archived("old/archive/plan.md") and archived("archive-2026-10-15.md")
    assert not archived("archive-plan.md") and not archived("archived-ideas.md")
    assert not archived("how-we-archive.md") and not archived("archives/plan.md")


def test_canonical_names():
    cfg = Config(aliases={"old_name": "new-name"}, drop=["docs"])
    assert canonical("Tide Pool + old_name + docs", cfg) == ["tide-pool", "new-name"]
    assert canonical("my_app", cfg) == canonical("my-app", cfg) == ["my-app"]


def test_decided_against():
    cases = {
        "2026-03-10, Sam: decided against a native mobile app.": True,
        "Not pushed; the release waits for the palette.": True,
        "Use MQTT, not HTTP polling.": True,          # a rejected alternative counts
        "That rules out a native app.": True,
        "Parked until spring.": True,
        "2026-03-05, Sam: MQTT for the probes; they sleep between readings.": False,
        "Favourite stations live in local storage.": False,
    }
    for text, against in cases.items():
        assert bool(AGAINST.search(text)) is against, text


def test_now_kinds():
    text = ("# P — NOW\n\n## State\n- s\n\n## Where things live\n- w\n\n## Next\n1. n\n\n"
            "## Decisions (incl. things decided against)\n- d\n- decided against e\n\n"
            "## Open threads (waiting on whom)\n- o\n\n## Gotchas\n- g\n\n## Misc\n- m\n")
    kinds = [now_kind(b) for b in split_blocks(text) if b.block == "item"]
    assert kinds == ["state", "where", "next", "decision", "decided_against", "open_thread", "gotcha", "note"]
