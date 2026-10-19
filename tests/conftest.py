import os
import shutil
from pathlib import Path

import pytest

from agent_memory.config import Config
from agent_memory.sources import encode

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "demo"


@pytest.fixture
def demo(tmp_path) -> Config:
    """A copy of the invented demo, laid out as a real install would see it."""
    shutil.copytree(DEMO, tmp_path / "demo", ignore=shutil.ignore_patterns("memory"))
    root = tmp_path / "demo"
    for proj in (DEMO / "memory").iterdir():
        shutil.copytree(proj, root / "claude" / "projects" / f"{encode(root / 'projects')}-{proj.name}" / "memory")
    return Config(claude_dir=root / "claude", notes_dir=root / "notes", project_dirs=[root / "projects"],
                  embed=False, env_file=tmp_path / "no.env")
