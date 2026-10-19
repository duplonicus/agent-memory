"""Settings: where your files live, where SurrealDB and Ollama listen.

Read from $AGENT_MEMORY_CONFIG, else ~/.config/agent-memory/config.toml, else the defaults below.
Credentials live in .env beside the config file (written by `agent-memory install`, mode 600);
environment variables of the same name win over it.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "agent-memory"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "agent-memory"
REPO = Path(__file__).resolve().parent.parent


def _path(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


@dataclass
class Config:
    claude_dir: Path = field(default_factory=lambda: Path.home() / ".claude")
    # The cross-project notes: NOW.md (what is going on everywhere) and LOG.md (one line per session).
    notes_dir: Path = field(default_factory=lambda: Path.home() / "agent-notes")
    # Every <dir>/<project>/NOW.md under these is a project. Its notes go in <project>/state/.
    project_dirs: list[Path] = field(default_factory=lambda: [Path.home() / "dev"])
    surreal_url: str = "http://127.0.0.1:8000"
    ns: str = "agent_memory"
    db: str = "state"
    embed_url: str = "http://127.0.0.1:11434"
    embed_model: str = "embeddinggemma"
    embed: bool = True
    brief_budget: int = 6000
    aliases: dict[str, str] = field(default_factory=dict)
    drop: list[str] = field(default_factory=list)
    max_deletes: int = 10
    env_file: Path = field(default_factory=lambda: CONFIG_DIR / ".env")

    @property
    def log_file(self) -> Path:
        return self.notes_dir / "LOG.md"

    @property
    def global_now(self) -> Path:
        return self.notes_dir / "NOW.md"

    def env(self) -> dict:
        """Credentials: .env beside the config, overridden by the process environment."""
        out: dict[str, str] = {}
        try:
            for line in self.env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
        out.update({k: v for k, v in os.environ.items() if k.startswith("AGENT_MEMORY_")})
        return out


def load(path: str | os.PathLike | None = None) -> Config:
    p = Path(path or os.environ.get("AGENT_MEMORY_CONFIG") or CONFIG_DIR / "config.toml")
    raw: dict = {}
    if p.is_file():
        with open(p, "rb") as f:
            raw = tomllib.load(f)
    cfg = Config()
    paths = raw.get("paths", {})
    if "claude_dir" in paths:
        cfg.claude_dir = _path(paths["claude_dir"])
    if "notes_dir" in paths:
        cfg.notes_dir = _path(paths["notes_dir"])
    if "project_dirs" in paths:
        cfg.project_dirs = [_path(d) for d in paths["project_dirs"]]
    s = raw.get("surreal", {})
    cfg.surreal_url = s.get("url", cfg.surreal_url)
    cfg.ns = s.get("ns", cfg.ns)
    cfg.db = os.environ.get("AGENT_MEMORY_DB") or s.get("db", cfg.db)
    e = raw.get("embed", {})
    cfg.embed_url = e.get("url", cfg.embed_url)
    cfg.embed_model = e.get("model", cfg.embed_model)
    cfg.embed = e.get("enabled", cfg.embed)
    cfg.brief_budget = raw.get("brief", {}).get("budget", cfg.brief_budget)
    pr = raw.get("projects", {})
    cfg.aliases = pr.get("aliases", {})
    cfg.drop = pr.get("drop", [])
    cfg.max_deletes = raw.get("sync", {}).get("max_deletes", cfg.max_deletes)
    if "env_file" in raw:
        cfg.env_file = _path(raw["env_file"])
    elif p.is_file():
        cfg.env_file = p.parent / ".env"
    return cfg
