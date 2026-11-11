import os
import shutil
import subprocess
import sys
from pathlib import Path

TREE = Path(__file__).resolve().parent.parent


def test_plain_pytest_imports_the_package_of_the_tree_it_runs_in(tmp_path):
    # A worktree shares main's .venv, whose editable install points at main's package.
    shutil.copy(TREE / "pyproject.toml", tmp_path)
    shutil.copytree(TREE / "agent_memory", tmp_path / "agent_memory", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_probe.py").write_text(
        "from pathlib import Path\n"
        "import agent_memory\n\n\n"
        "def test_tree():\n"
        "    assert Path(agent_memory.__file__).resolve().parent.parent == Path(__file__).resolve().parent.parent\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTEST_ADDOPTS")}
    run = subprocess.run([Path(sys.executable).parent / "pytest", "-q", "-p", "no:cacheprovider"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout
