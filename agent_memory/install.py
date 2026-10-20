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
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import CONFIG_DIR, REPO, STATE_DIR, Config, load
from .db import apply_schema

TEMPLATES = REPO / "templates"
# (event, hook name, matcher) for every hook the installer adds; agent_memory/hook.py runs them.
HOOKS = [("SessionStart", "session-start", None), ("Stop", "stop", None), ("UserPromptSubmit", "prompt", None),
         ("PreToolUse", "pre-write", "Write"), ("PreCompact", "pre-compact", None)]


def _ours(hook: dict, name: str) -> bool:
    """Is this settings.json hook entry agent-memory's `name` hook? (Before 0.1 the brief had no name.)"""
    cmd = str(hook.get("command", ""))
    if "agent_memory hook" not in cmd:
        return False
    rest = cmd.split("agent_memory hook", 1)[1].strip()
    return rest == name or (name == "session-start" and rest == "")
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
        port = urllib.parse.urlsplit(cfg.surreal_url).port or 8000
        if self._up(f"{cfg.surreal_url}/health"):
            print(f"SurrealDB answers at {cfg.surreal_url}")
        elif shutil.which("docker") is None:
            self.todo.append("Install Docker (or run SurrealDB 3.3.4 yourself), then rerun `agent-memory install`.")
            return False
        elif self._port_taken(port):
            self.todo.append(f"Port {port} is already in use by something that isn't answering as SurrealDB. Pick a free "
                             f"port: set [surreal] url in {CONFIG_DIR / 'config.toml'} to it, then rerun the installer.")
            return False
        elif self.ask(f"Start SurrealDB 3.3.4 in Docker (compose project agent-memory, loopback port {port})?"):
            try:
                subprocess.run(["docker", "compose", "-f", str(REPO / "compose.yaml"), "-p", "agent-memory",
                                "--env-file", str(cfg.env_file), "up", "-d"], check=True,
                               env={**os.environ, "AGENT_MEMORY_PORT": str(port)})
            except (subprocess.CalledProcessError, OSError) as e:
                self.todo.append(f"Starting SurrealDB in Docker failed ({e}); the docker output above says why. "
                                 f"Is Docker running?")
                return False
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
        try:
            errors = apply_schema(cfg)
        except urllib.error.HTTPError as e:
            # A SurrealDB that is someone else's (another project's, with its own root password) refuses ours.
            self.todo.append(f"SurrealDB at {cfg.surreal_url} refused the root login from {cfg.env_file} (HTTP {e.code}). "
                             f"If that server belongs to something else, point [surreal] url at a free port and rerun.")
            return False
        if errors:
            self.todo.append("Schema errors: " + "; ".join(errors))
            return False
        self.done.append(f"applied the schema (ns {cfg.ns}, db {cfg.db})")
        return True

    @staticmethod
    def _port_taken(port: int) -> bool:
        import socket
        with socket.socket() as sock:
            sock.settimeout(1)
            return sock.connect_ex(("127.0.0.1", port)) == 0

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
        hooks = data.setdefault("hooks", {})
        missing = [(event, name, matcher) for event, name, matcher in HOOKS
                   if not any(_ours(h, name) for group in hooks.get(event, []) for h in group.get("hooks", []))]
        if not missing:
            print("agent-memory hooks already installed")
        elif self.ask(f"Add agent-memory's hooks to {settings}? ({', '.join(n for _, n, _ in missing)}: the session-start "
                      f"brief, plus the nudges that keep NOW.md and LOG.md current; see agent_memory/handoff.py)"):
            if settings.exists():
                print(f"  backup: {self.backup(settings)}")
            for event, name, matcher in missing:
                cmd = f"-m agent_memory hook {name}"
                if os.name == "nt":
                    # Claude Code runs hooks in Git Bash on Windows, or PowerShell without it; pin PowerShell so
                    # the command means the same thing either way (& calls a quoted path).
                    hook = {"type": "command", "command": f'& "{exe}" {cmd}', "shell": "powershell", "timeout": 15}
                else:
                    hook = {"type": "command", "command": f'"{exe}" {cmd}', "timeout": 15}
                group = {"matcher": matcher, "hooks": [hook]} if matcher else {"hooks": [hook]}
                hooks.setdefault(event, []).append(group)
            settings.write_text(encoding="utf-8", data=json.dumps(data, indent=2) + "\n")
            self.done.append(f"added {len(missing)} hook(s) to {settings}")
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

    @staticmethod
    def _systemctl(*args: str) -> bool:
        try:
            return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=False).returncode == 0
        except OSError:
            return False

    @staticmethod
    def _write_unit(unit: Path, exe: Path) -> None:
        unit.parent.mkdir(parents=True, exist_ok=True)
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

    # 6. The sync service
    def service(self, cfg: Config) -> None:
        exe = Path(sys.executable)
        system = platform.system()
        if system == "Linux" and shutil.which("systemctl"):
            unit_dir = Path.home() / ".config" / "systemd" / "user"
            unit = unit_dir / UNIT
            # Check the service, not the file: a first run can write the unit and then fail to enable it (WSL
            # without systemd), and a rerun must still enable it.
            if unit.exists():
                if self._systemctl("is-enabled", UNIT) and self._systemctl("is-active", UNIT):
                    print(f"{UNIT} is enabled and running")
                    return
                if not self.ask(f"{unit} exists but the service is not running. Enable and start it?"):
                    return
            elif not self.ask(f"Install and start the sync service ({unit}, systemd user unit)?"):
                return
            else:
                self._write_unit(unit, exe)
            try:
                for args in (["daemon-reload"], ["enable", "--now", UNIT]):
                    subprocess.run(["systemctl", "--user", *args], check=True, capture_output=True, text=True)
            except (OSError, subprocess.CalledProcessError) as e:
                why = (getattr(e, "stderr", "") or str(e)).strip().splitlines()
                self.todo.append(f"Start the sync service: `systemctl --user enable --now {UNIT}` failed "
                                 f"({why[0] if why else type(e).__name__}). On WSL, turn systemd on ([boot] "
                                 f"systemd=true in /etc/wsl.conf, then `wsl --shutdown`), then rerun "
                                 f"`agent-memory install`.")
                return
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
        mark_installed()
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


def mark_installed(state_dir: Path = STATE_DIR) -> None:
    """The audit counts unlogged sessions from the first install on (audit.INSTALLED's mtime), so a rerun
    leaves the marker as it is."""
    state_dir.mkdir(parents=True, exist_ok=True)
    marker = state_dir / "installed"
    if not marker.exists():
        marker.touch()


def main(args: list[str]) -> None:
    Installer(args).run()
