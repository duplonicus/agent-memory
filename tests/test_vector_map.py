"""examples/vector-map/build.py: --hide must match however the person spells the project."""
import importlib.util

from agent_memory.config import Config
from conftest import REPO

spec = importlib.util.spec_from_file_location("vector_map_build", REPO / "examples" / "vector-map" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_hide_takes_the_folder_name_or_any_spelling():
    cfg = Config(aliases={"old_client": "my-client"})
    argv = ["map.html", "--hide", "My_Client", "--hide", "tide pool", "--hide", "old_client"]
    assert build.hidden(argv, cfg) == {"my-client", "tide-pool"}
    assert build.hidden(["map.html"], cfg) == set()
