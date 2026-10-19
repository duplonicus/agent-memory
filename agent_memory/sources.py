"""Which files are memory, what kind each one is, and which project it belongs to.

    <claude_dir>/CLAUDE.md, <claude_dir>/rules/*.md          rules, project "global"
    <claude_dir>/projects/<encoded cwd>/memory/*.md          memory (MEMORY.md is the index)
    <notes_dir>/NOW.md, LOG.md, other *.md                   now, log, doc; project "global"
    <project_dir>/<name>/NOW.md                              now, project <name>
    <project_dir>/<name>/state/**/*.md                       doc, project <name>
    <project_dir>/<name>/CLAUDE.md                           project_claude
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config

SKIP_DIRS = {"node_modules", ".git", ".venv"}
GENERATED_MARKER = b"<!-- agent-memory: generated"


@dataclass(frozen=True)
class Source:
    path: str       # absolute
    kind: str       # rules | memory | memory_index | now | log | doc | project_claude
    project: str
    archived: bool = False
    # What ids are hashed from. Empty = the path. A file that moved keeps the locator it had, so its
    # ids, vectors and graph edges survive the move (see Importer._resolve).
    locator: str = ""

    @property
    def key(self) -> str:
        return self.locator or self.path


def encode(path: Path | str) -> str:
    """Claude Code's folder name for a working directory under ~/.claude/projects: every character
    that is not a letter or digit becomes '-' (/home/me/dev/my_app -> -home-me-dev-my-app,
    C:\\Users\\me\\dev -> C--Users-me-dev)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def memory_project(folder: str, cfg: Config) -> str | None:
    """Project name for an encoded cwd folder: what is left after the longest project dir prefix.
    A session started in the home folder is "home"; anything else keeps its encoded name."""
    prefixes = sorted((encode(d) + "-" for d in cfg.project_dirs), key=len, reverse=True)
    for prefix in prefixes:
        if folder.startswith(prefix) and len(folder) > len(prefix):
            return folder[len(prefix):]
    if folder == encode(Path.home()):
        return "home"
    return folder.strip("-") or None


def archived(rel: str) -> bool:
    """Old copies stay in the database but out of search: anything under an archive/ folder, and any
    file whose name says archive (a dated copy of a NOW.md, say)."""
    parts = rel.lower().replace("\\", "/").split("/")
    return any(p == "archive" for p in parts[:-1]) or "archive" in parts[-1]


def _generated(path: Path) -> bool:
    """A report written FROM the database is not imported back, or the database would describe itself."""
    try:
        with path.open("rb") as f:
            return f.read(len(GENERATED_MARKER)) == GENERATED_MARKER
    except OSError:
        return False


def _md(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [p for p in sorted(root.rglob("*.md")) if not SKIP_DIRS & set(p.relative_to(root).parts)]


def enumerate_sources(cfg: Config) -> list[Source]:
    out: list[Source] = []
    seen: set[str] = set()

    def add(path: Path, kind: str, project: str, arch: bool = False):
        if path.is_file() and not _generated(path) and str(path) not in seen:
            seen.add(str(path))
            out.append(Source(str(path), kind, project, arch))

    claude = cfg.claude_dir
    add(claude / "CLAUDE.md", "rules", "global")
    for p in sorted((claude / "rules").glob("*.md")):
        add(p, "rules", "global")
    projects = claude / "projects"
    if projects.is_dir():
        for folder in sorted(projects.iterdir()):
            # A symlink to a sibling folder is the same memory seen twice; read the real folder only.
            if folder.is_symlink() and folder.resolve().parent == projects.resolve():
                continue
            mem = folder / "memory"
            project = memory_project(folder.name, cfg)
            if not mem.is_dir() or project is None:
                continue
            for p in sorted(mem.glob("*.md")):
                add(p, "memory_index" if p.name == "MEMORY.md" else "memory", project)

    notes = cfg.notes_dir
    for p in _md(notes):
        rel = p.relative_to(notes).as_posix()
        kind = {"NOW.md": "now", "LOG.md": "log"}.get(rel, "doc")
        add(p, kind, "global", archived(rel))

    for base in cfg.project_dirs:
        if not base.is_dir():
            continue
        for proj in sorted(base.iterdir()):
            if not proj.is_dir() or proj.resolve() == notes.resolve():
                continue
            now = proj / "NOW.md"
            if now.is_file():
                add(now.resolve(), "now", proj.name)
                for p in _md(proj / "state"):
                    add(p, "doc", proj.name, archived(p.relative_to(proj / "state").as_posix()))
            add(proj / "CLAUDE.md", "project_claude", proj.name)
    return out
