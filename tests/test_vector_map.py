"""examples/vector-map/build.py: --hide must match however the person spells the project."""
import importlib.util

from conftest import REPO

from agent_memory.config import Config

spec = importlib.util.spec_from_file_location("vector_map_build", REPO / "examples" / "vector-map" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_hide_takes_the_folder_name_or_any_spelling():
    cfg = Config(aliases={"old_client": "my-client"})
    argv = ["map.html", "--hide", "My_Client", "--hide", "tide pool", "--hide", "old_client"]
    assert build.hidden(argv, cfg) == {"my-client", "tide-pool"}
    assert build.hidden(["map.html"], cfg) == set()


def test_hide_still_hides_a_dropped_project_under_the_name_its_dots_carry():
    cfg = Config(drop=["scratch"])
    hide = build.hidden(["map.html", "--hide", "scratch"], cfg)
    assert hide == {"scratch"}
    dot_project = (build.canonical("scratch", cfg) or ["scratch"])[0]
    assert dot_project in hide


def test_hide_report_always_says_what_was_hidden():
    assert build.hide_report({"scratch"}, {"scratch", "web"}) == ["text hidden for: scratch"]
    lines = build.hide_report({"nope"}, {"web"})
    assert lines[0] == "text hidden for: none"
    assert lines[1].startswith("WARN: no notes in nope")
