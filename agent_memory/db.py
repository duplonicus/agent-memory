"""Connections to SurrealDB. The sync daemon and queries sign in as the namespace user (EDITOR) from
the .env beside the config; root is for the schema and backups only. Nothing here prints a credential."""
from __future__ import annotations

import json
import urllib.request
from base64 import b64encode
from pathlib import Path

from surrealdb import Surreal

from .config import Config

HERE = Path(__file__).resolve().parent


def connect(cfg: Config) -> Surreal:
    env = cfg.env()
    conn = Surreal(cfg.surreal_url)
    conn.signin({"username": env["AGENT_MEMORY_USER"], "password": env["AGENT_MEMORY_PASS"], "namespace": cfg.ns})
    conn.use(cfg.ns, cfg.db)
    return conn


def sql(cfg: Config, query: str, root: bool = False, db: str | None = None) -> list[dict]:
    """POST SurrealQL to /sql and return the per-statement results (status, result)."""
    env = cfg.env()
    keys = ("AGENT_MEMORY_ROOT_USER", "AGENT_MEMORY_ROOT_PASS") if root else ("AGENT_MEMORY_USER", "AGENT_MEMORY_PASS")
    missing = [k for k in keys if not env.get(k)]
    if missing:  # no built-in fallback password: a default credential would end up in someone's database
        raise RuntimeError(f"{', '.join(missing)} not set; run `agent-memory install` or add them to {cfg.env_file}")
    user, pw = env[keys[0]], env[keys[1]]
    headers = {"Accept": "application/json", "surreal-ns": cfg.ns, "surreal-db": db or cfg.db,
               "Authorization": "Basic " + b64encode(f"{user}:{pw}".encode()).decode()}
    if not root:
        headers["surreal-auth-ns"] = cfg.ns
    req = urllib.request.Request(f"{cfg.surreal_url}/sql", data=query.encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def apply_schema(cfg: Config, db: str | None = None) -> list[str]:
    """Create the namespace, database and namespace user, then apply schema.surql and functions.surql
    (all idempotent). Returns the errors, empty when it worked."""
    env = cfg.env()
    user, pw = env["AGENT_MEMORY_USER"], env["AGENT_MEMORY_PASS"]
    if not user.replace("_", "").isalnum() or "'" in pw or "\\" in pw:
        raise ValueError("AGENT_MEMORY_USER must be alphanumeric and the password must not contain ' or \\")
    db = db or cfg.db
    setup = (f"DEFINE NAMESPACE IF NOT EXISTS {cfg.ns}; USE NS {cfg.ns}; DEFINE DATABASE IF NOT EXISTS {db}; "
             f"DEFINE USER OVERWRITE {user} ON NAMESPACE PASSWORD '{pw}' ROLES EDITOR;")
    errors = []
    for q in (setup, (HERE / "schema.surql").read_text(encoding="utf-8"), (HERE / "functions.surql").read_text(encoding="utf-8")):
        for r in sql(cfg, q, root=True, db=db):
            if r.get("status") != "OK" and "already exists" not in str(r.get("result")):
                errors.append(str(r.get("result")))
    return errors
