"""The installer's service step and install marker, with systemctl and the home folder faked: nothing here
touches the real systemd, Docker or SurrealDB."""
import os
import subprocess
from pathlib import Path

import pytest

from agent_memory import install
from agent_memory.config import Config


@pytest.fixture
def linux(tmp_path, monkeypatch):
    """A Linux box with systemctl on PATH, whose user units live under tmp_path. `state` says what the fake
    systemctl reports; `calls` records every command."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/bin/" + name)
    state = {"booted": True, "enabled": False}
    calls = []

    def run(cmd, check=False, **kw):
        calls.append(cmd[2:])
        verb = cmd[2]
        if not state["booted"]:
            rc, err = 1, "System has not been booted with systemd as init system (PID 1). Can't operate."
        elif verb in ("is-enabled", "is-active"):
            rc, err = (0 if state["enabled"] else 1), ""
        else:
            rc, err = 0, ""
            if verb == "enable":
                state["enabled"] = True
        if check and rc:
            raise subprocess.CalledProcessError(rc, cmd, "", err)
        return subprocess.CompletedProcess(cmd, rc, "", err)

    monkeypatch.setattr(install.subprocess, "run", run)
    unit = tmp_path / ".config" / "systemd" / "user" / install.UNIT
    return type("Linux", (), {"state": state, "calls": calls, "unit": unit})


def test_a_failed_enable_is_a_todo_and_a_rerun_enables_it(linux):
    linux.state["booted"] = False  # WSL without systemd: systemctl exists, but every call fails
    first = install.Installer(["--yes"])
    first.service(Config())
    assert linux.unit.exists()
    assert any("systemctl --user enable --now" in t for t in first.todo) and not first.done
    linux.state["booted"] = True  # the person turns systemd on and reruns the installer
    linux.calls.clear()
    second = install.Installer(["--yes"])
    second.service(Config())
    assert ["enable", "--now", install.UNIT] in linux.calls
    assert linux.state["enabled"] and second.done and not second.todo


def test_an_enabled_running_service_is_left_alone(linux):
    linux.unit.parent.mkdir(parents=True)
    linux.unit.write_text("[Unit]\n", encoding="utf-8")
    linux.state["enabled"] = True
    inst = install.Installer(["--yes"])
    inst.service(Config())
    assert not [c for c in linux.calls if c[0] not in ("is-enabled", "is-active")]
    assert linux.unit.read_text(encoding="utf-8") == "[Unit]\n" and not inst.done and not inst.todo


def test_a_rerun_keeps_the_install_time(tmp_path):
    """The audit counts unlogged sessions from the install on; a rerun must not move that start."""
    install.mark_installed(tmp_path)
    marker = tmp_path / "installed"
    os.utime(marker, (1000, 1000))
    install.mark_installed(tmp_path)
    assert marker.stat().st_mtime == 1000
