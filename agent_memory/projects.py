"""Project names. One project gets spelled several ways ("my_app" the folder, "my-app" in a LOG line,
"My App" by hand), and a LOG line can name several ("api + web"). Rows keep the name as written;
graph edges and project nodes use the canonical one: lowercased, runs of other characters turned
into '-', then [projects.aliases] from the config."""
from __future__ import annotations

import re

from .config import Config


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def canonical(raw: str, cfg: Config) -> list[str]:
    """Canonical project names for a raw project string, in order, without duplicates."""
    aliases = {norm(k): norm(v) for k, v in cfg.aliases.items()}
    drop = {norm(d) for d in cfg.drop}
    out: list[str] = []
    for part in raw.split(" + "):
        key = norm(part)
        if not key or key in drop:
            continue
        name = aliases.get(key, key)
        if name not in out:
            out.append(name)
    return out
