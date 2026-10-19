"""`agent-memory install`: set up the config, SurrealDB, the schema, Claude Code hooks and skills, and the
sync service. Every step is skipped when already done, and every change outside this repo is asked first
(--yes answers yes to all). Nothing is overwritten: settings.json and CLAUDE.md are backed up, then
added to; skills that already exist are left alone.

    agent-memory install [--yes] [--notes DIR] [--projects DIR[,DIR]] [--no-service] [--no-claude]
"""
from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import CONFIG_DIR, REPO, STATE_DIR, Config, load
from .db import apply_schema

TEMPLATES = REPO / "templates"
HOOK_MARK = "agent_memory hook"
UNIT = "agent-memory-sync.service"
TASK = "agent-memory sync"


class Installer:
    def __init__(self, args: list[str]):
        self.yes = "--yes" in args or "-y" in args
        self.args = args
        self.done: list[str] = []
        self.todo: list[str] = []

    def opt(self, name: str) -> str | None:
        return self.args[self.args.index(name) + 1] if name in self.args[:-1] else None

    def ask(self, question: str) -> bool:
        if self.yes:
            print(f"{question} [y/N] y (--yes)")
            return True
        if not sys.stdin.isatty():
            print(f"{question} [y/N] n (no terminal; rerun with --yes)")
            return False
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")

    @staticmethod
    def backup(path: Path) -> Path:
        dest = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(path, dest)
        return dest

    # 1. config and credentials
    def config(self) -> Config:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg_file = CONFIG_DIR / "config.toml"
        if not cfg_file.exists():
            text = (TEMPLATES / "config.toml").read_text(encoding="utf-8")
            if notes := self.opt("--notes"):
                text = text.replace('notes_dir = "~/agent-notes"', f'notes_dir = "{notes}"')
            if projects := self.opt("--projects"):
                dirs = ", ".join(f'"{d.strip()}"' for d in projects.split(","))
                text = text.replace('project_dirs = ["~/dev"]', f"project_dirs = [{dirs}]")
            cfg_file.write_text(encoding="utf-8", data=text)
            self.done.append(f"wrote {cfg_file}")
        env = CONFIG_DIR / ".env"
        if not env.exists():
            env.write_text(encoding="utf-8", data="# agent-memory credentials; keep this file private\n"
                           f"AGENT_MEMORY_ROOT_USER=root\nAGENT_MEMORY_ROOT_PASS={secrets.token_hex(16)}\n"
                           f"AGENT_MEMORY_USER=agent_memory\nAGENT_MEMORY_PASS={secrets.token_hex(16)}\n")
            os.chmod(env, 0o600)
            self.done.append(f"wrote {env} (random passwords, mode 600)")
        cfg = load(cfg_file)
        cfg.notes_dir.mkdir(parents=True, exist_ok=True)
        for name in ("NOW.md", "LOG.md"):
            if not (cfg.notes_dir / name).exists():
                text = (TEMPLATES / name).read_text(encoding="utf-8")
                if name == "NOW.md":
                    text = "# NOW — start here\n\n## Open to-do\n- none\n\n## Where things live\n- One NOW.md per project, in its folder; LOG.md beside this file.\n"
                (cfg.notes_dir / name).write_text(encoding="utf-8", data=text)
                self.done.append(f"wrote {cfg.notes_dir / name}")
        return cfg

    # 2. SurrealDB
    def database(self, cfg: Config) -> bool:
        if self._up(f"{cfg.surreal_url}/health"):
            print(f"SurrealDB answers at {cfg.surreal_url}")
        elif shutil.which("docker") is None:
            self.todo.append("Install Docker (or run SurrealDB 3.3.4 yourself), then rerun `agent-memory install`.")
            return False
        elif self.ask(f"Start SurrealDB 3.3.4 in Docker (compose project agent-memory, loopback port 8000)?"):
            subprocess.run(["docker", "compose", "-f", str(REPO / "compose.yaml"), "-p", "agent-memory",
                            "--env-file", str(cfg.env_file), "up", "-d"], check=True)
            for _ in range(60):
                if self._up(f"{cfg.surreal_url}/health"):
                    break
                time.sleep(0.5)
            else:
                self.todo.append("SurrealDB did not answer after 30 s: `docker compose -p agent-memory logs`.")
                return False
            self.done.append("started SurrealDB (docker compose project agent-memory)")
        else:
            self.todo.append("Start SurrealDB 3.3.4, then rerun `agent-memory install`.")
            return False
        errors = apply_schema(cfg)
        if errors:
            self.todo.append("Schema errors: " + "; ".join(errors))
            return False
        self.done.append(f"applied the schema (ns {cfg.ns}, db {cfg.db})")
        return True

    # 3. Ollama and the embedding model
    def embeddings(self, cfg: Config) -> None:
        if not cfg.embed:
            return
        if not self._up(f"{cfg.embed_url}/api/version"):
            self.todo.append(f"Ollama is not answering at {cfg.embed_url}: install it (ollama.com) for search by "
                             f"meaning. Keyword search works without it.")
            return
        try:
            with urllib.request.urlopen(f"{cfg.embed_url}/api/tags", timeout=5) as r:
                names = {m["name"].split(":")[0] for m in json.loads(r.read())["models"]}
        except Exception:  # noqa: BLE001
            names = set()
        if cfg.embed_model in names:
            print(f"Ollama has {cfg.embed_model}")
        elif self.ask(f"Download the embedding model {cfg.embed_model} into Ollama (about 620 MB)?"):
            req = urllib.request.Request(f"{cfg.embed_url}/api/pull", method="POST",
                                         data=json.dumps({"model": cfg.embed_model, "stream": False}).encode())
            with urllib.request.urlopen(req, timeout=3600) as r:
                r.read()
            self.done.append(f"pulled {cfg.embed_model}")
        else:
            self.todo.append(f"`ollama pull {cfg.embed_model}` when you want search by meaning.")

    # 4. Claude Code: hook, skills, CLAUDE.md
    def claude(self, cfg: Config) -> None:
        claude = cfg.claude_dir
        claude.mkdir(parents=True, exist_ok=True)
        exe = Path(sys.executable).as_posix()
        settings = claude / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
        hooks = data.setdefault("hooks", {}).setdefault("SessionStart", [])
        if HOOK_MARK in json.dumps(hooks):
            print("SessionStart hook already installed")
        elif self.ask(f"Add the session-start brief hook to {settings}?"):
            if settings.exists():
                print(f"  backup: {self.backup(settings)}")
            if os.name == "nt":
                # Claude Code runs hooks in Git Bash on Windows, or PowerShell without it; pin PowerShell so
                # the command means the same thing either way (& calls a quoted path).
                hook = {"type": "command", "command": f'& "{exe}" -m {HOOK_MARK}', "shell": "powershell", "timeout": 15}
            else:
                hook = {"type": "command", "command": f'"{exe}" -m {HOOK_MARK}', "timeout": 15}
            hooks.append({"hooks": [hook]})
            settings.write_text(encoding="utf-8", data=json.dumps(data, indent=2) + "\n")
            self.done.append(f"added the SessionStart hook to {settings}")
        for name in ("sum", "search"):
            dest = claude / "skills" / name
            if dest.exists():
                print(f"skill {name} exists at {dest}; left alone")
                continue
            if self.ask(f"Add the /{name} skill to {dest}?"):
                dest.mkdir(parents=True)
                shutil.copy2(REPO / "skills" / name / "SKILL.md", dest / "SKILL.md")
                self.done.append(f"added /{name}")
        md = claude / "CLAUDE.md"
        snippet = (TEMPLATES / "CLAUDE.md").read_text(encoding="utf-8")
        if md.exists() and "<!-- agent-memory:start -->" in md.read_text(encoding="utf-8"):
            print("CLAUDE.md already has the agent-memory section")
        elif self.ask(f"Append the memory conventions (templates/CLAUDE.md, ~30 lines) to {md}?"):
            if md.exists():
                print(f"  backup: {self.backup(md)}")
            with md.open("a", encoding="utf-8") as f:
                f.write(("\n" if md.exists() and md.stat().st_size else "") + snippet)
            self.done.append(f"appended the conventions to {md}")

    # 5. `agent-memory` on PATH, for the skills, the CLAUDE.md section and you
    def command(self) -> None:
        if shutil.which("agent-memory"):
            print(f"agent-memory is on PATH ({shutil.which('agent-memory')})")
            return
        exe = Path(sys.executable).parent / ("agent-memory.exe" if os.name == "nt" else "agent-memory")
        if os.name == "nt":
            self.todo.append(f"Add {exe.parent} to your PATH so `agent-memory` works in any shell.")
            return
        link = Path.home() / ".local" / "bin" / "agent-memory"
        if link.exists() or link.is_symlink():
            return
        if self.ask(f"Link {link} -> {exe}, so `agent-memory` works in any shell?"):
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(exe)
            self.done.append(f"linked {link}")
            if str(link.parent) not in os.environ.get("PATH", "").split(os.pathsep):
                self.todo.append(f"Add {link.parent} to your PATH.")

    # 6. The sync service
    def service(self, cfg: Config) -> None:
        exe = Path(sys.executable)
        system = platform.system()
        if system == "Linux" and shutil.which("systemctl"):
            unit_dir = Path.home() / ".config" / "systemd" / "user"
            unit = unit_dir / UNIT
            if unit.exists():
                print(f"{unit} exists")
                return
            if not self.ask(f"Install and start the sync service ({unit}, systemd user unit)?"):
                return
            unit_dir.mkdir(parents=True, exist_ok=True)
            unit.write_text(encoding="utf-8", data=f"""[Unit]
Description=agent-memory: copies your memory files into SurrealDB, one way
After=network.target

[Service]
Type=simple
ExecStart={exe} -m agent_memory daemon
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
""")
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", UNIT], check=True)
            self.done.append(f"started {UNIT} (journalctl --user -u {UNIT})")
        elif system == "Windows":
            pyw = exe.with_name("pythonw.exe")
            pyw = pyw if pyw.exists() else exe
            if not self.ask(f"Register a Task Scheduler task '{TASK}' that runs the sync at logon, and start it now?"):
                return
            subprocess.run(["schtasks", "/Create", "/F", "/TN", TASK, "/SC", "ONLOGON",
                            "/TR", f'"{pyw}" -m agent_memory daemon'], check=True)
            subprocess.run(["schtasks", "/Run", "/TN", TASK], check=True)
            self.done.append(f"registered and started the '{TASK}' task")
        else:
            self.todo.append(f"Run `{exe} -m agent_memory daemon` in the background (launchd support is not "
                             f"written yet), or `agent-memory sync` by hand.")

    @staticmethod
    def _up(url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=3):
                return True
        except Exception:  # noqa: BLE001
            return False

    def run(self) -> None:
        cfg = self.config()
        db_ok = self.database(cfg)
        self.embeddings(cfg)
        self.command()
        if "--no-claude" not in self.args:
            self.claude(cfg)
        if db_ok and "--no-service" not in self.args:
            self.service(cfg)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "installed").touch(exist_ok=True)
        if db_ok:
            from .db import connect
            from .importer import Importer
            stats = Importer(connect(cfg), cfg, log=lambda *a: None).sync()
            self.done.append(f"sync: {stats['files']} files, {stats['entries']} entries, {stats['logs']} LOG lines")
        print("\nDone:" if self.done else "\nNothing changed.")
        for d in self.done:
            print(f"  - {d}")
        if self.todo:
            print("Still to do:")
            for t in self.todo:
                print(f"  - {t}")
        print("\nTry it: `agent-memory demo`, then start Claude Code in a project folder (cd ~/dev/<project> && claude).")


def main(args: list[str]) -> None:
    Installer(args).run()
