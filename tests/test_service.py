"""Datas as a background service on Linux (datas/service.py): the file it writes and the
commands it gives to systemd. The real start is checked by the installer builds."""

from __future__ import annotations

import subprocess
import sys

import pytest

from datas import service
from datas.words import Problem


class Systemd:
    """Stands in for systemctl and loginctl; remembers what was asked."""

    def __init__(self, start_ok: bool = True, linger: bool = False, may_linger: bool = True):
        self.asked: list[list[str]] = []
        self.start_ok, self.linger, self.may_linger = start_ok, linger, may_linger

    def __call__(self, cmd, **kw):
        self.asked.append(list(cmd))
        if cmd[:2] == ["systemctl", "--user"] and "enable" in cmd:
            if not self.start_ok:
                return subprocess.CompletedProcess(
                    cmd, 1, "", "Failed to connect to bus: No medium found\n"
                )
        if cmd[:2] == ["systemctl", "--user"] and "is-active" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "active\n", "")
        if cmd[0] == "loginctl" and cmd[1] == "enable-linger":
            self.linger = self.linger or self.may_linger
        if cmd[0] == "loginctl" and cmd[1] == "show-user":
            return subprocess.CompletedProcess(
                cmd, 0, f"Linger={'yes' if self.linger else 'no'}\n", ""
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def linux(tmp_path, monkeypatch):
    monkeypatch.setattr(service.platform, "system", lambda: "Linux")
    monkeypatch.setattr(service.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("DATAS_HOME", raising=False)
    return tmp_path


def test_the_service_file_starts_this_copy_without_a_window(linux, monkeypatch):
    text = service.unit_text(["/opt/datas/datas-cli", "serve", "--no-browser"])
    assert "ExecStart=/opt/datas/datas-cli serve --no-browser\n" in text
    assert "Restart=on-failure" in text and "WantedBy=default.target" in text
    assert "User=" not in text  # a user service: it runs as the person, never as the administrator
    # a folder with spaces or a % sign must not break the line systemd reads
    odd = service.unit_text(["/home/ana maría/My Apps 100%/datas-cli", "serve", "--no-browser"])
    assert 'ExecStart="/home/ana maría/My Apps 100%%/datas-cli" serve --no-browser\n' in odd
    # a copy that keeps its data in its own folder keeps doing so as a service
    monkeypatch.setenv("DATAS_HOME", "/srv/datas data")
    assert service.command()[-2:] == ["--home", "/srv/datas data"]
    assert 'ExecStart=x serve --no-browser --home "/srv/datas data"' in service.unit_text(
        ["x", "serve", "--no-browser", "--home", "/srv/datas data"]
    )
    monkeypatch.delenv("DATAS_HOME")
    # from source it is "python -m datas"; installed, the command-line program beside the app
    assert (
        service.command()[-2:] == ["serve", "--no-browser"]
        and service.command()[0] == sys.executable
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(linux / "Datas"))
    (linux / "datas-cli").write_text("")
    assert service.command() == [str(linux / "datas-cli"), "serve", "--no-browser"]


def test_install_starts_it_and_asks_to_start_at_boot(linux):
    sd = Systemd()
    r = service.install(run=sd)
    unit = linux / "config" / "systemd" / "user" / "datas.service"
    assert r == {"file": str(unit), "started": True, "at_boot": True, "notes": []}
    assert unit.read_text(encoding="utf-8").startswith("[Unit]")
    assert ["systemctl", "--user", "daemon-reload"] in sd.asked
    assert ["systemctl", "--user", "enable", "--now", "datas.service"] in sd.asked
    assert ["loginctl", "enable-linger"] in sd.asked
    assert not any("sudo" in c for cmd in sd.asked for c in cmd)  # never asks for the administrator
    st = service.status(run=sd)
    assert st["installed"] and st["running"] and st["at_boot"]
    # removing it stops it and deletes only its own file
    r = service.remove(run=sd)
    assert r["removed"] and not unit.exists()
    assert ["systemctl", "--user", "disable", "--now", "datas.service"] in sd.asked
    assert service.remove(run=sd)["removed"] is False


def test_what_the_person_is_told_when_it_cannot_do_everything(linux):
    # the system does not let this user start programs at boot: one plain sentence with the fix
    r = service.install(run=Systemd(may_linger=False))
    assert r["started"] and not r["at_boot"]
    assert len(r["notes"]) == 1 and "sudo loginctl enable-linger" in r["notes"][0]
    # no user systemd in this session (a container, some remote sessions)
    r = service.install(run=Systemd(start_ok=False))
    assert not r["started"] and "datas-cli serve --no-browser" in r["notes"][0]
    assert "No medium found" in r["notes"][0]


def test_other_systems_get_a_plain_answer(monkeypatch):
    monkeypatch.setattr(service.platform, "system", lambda: "FreeBSD")
    with pytest.raises(Problem) as e:
        service.install()
    assert "Linux, Windows and macOS" in str(e.value)
    assert "Linux, Windows y macOS" in e.value.say("es")
    monkeypatch.setattr(service.platform, "system", lambda: "Linux")
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    with pytest.raises(Problem) as e:
        service.status()
    assert "no systemd" in str(e.value)


class Launchd:
    def __init__(self, bootstrap_ok: bool = True):
        self.asked: list[list[str]] = []
        self.loaded, self.bootstrap_ok = False, bootstrap_ok

    def __call__(self, cmd, **kw):
        self.asked.append(list(cmd))
        verb = cmd[1]
        if verb in ("bootstrap", "load"):
            if verb == "bootstrap" and not self.bootstrap_ok:
                return subprocess.CompletedProcess(
                    cmd, 5, "", "Bootstrap failed: 5: Input/output error"
                )
            self.loaded = True
        if verb in ("bootout", "unload"):
            ok, self.loaded = self.loaded, False
            return subprocess.CompletedProcess(cmd, 0 if ok else 3, "", "")
        if verb == "print":
            return subprocess.CompletedProcess(cmd, 0 if self.loaded else 113,
                                               "state = running\n" if self.loaded else "", "")  # fmt: skip
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_on_a_mac_it_is_a_launch_agent_of_the_person(tmp_path, monkeypatch):
    import plistlib

    monkeypatch.setattr(service.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(service.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(service.os, "getuid", lambda: 501, raising=False)
    ld = Launchd()
    r = service.install(run=ld)
    plist = tmp_path / "Library" / "LaunchAgents" / "ar.datas.service.plist"
    assert r["started"] and r["file"] == str(plist) and "log in" in r["notes"][-1]
    d = plistlib.loads(plist.read_bytes())
    assert d["Label"] == "ar.datas.service" and d["RunAtLoad"] is True
    assert d["ProgramArguments"][-4:] == ["serve", "--no-browser", "--home", str(tmp_path / "data")]
    assert d["KeepAlive"] == {"SuccessfulExit": False}
    assert ["launchctl", "bootstrap", "gui/501", str(plist)] in ld.asked
    assert service.status(run=ld)["running"] and service.status(run=ld)["installed"]
    assert not any("sudo" in c for cmd in ld.asked for c in cmd)
    r = service.remove(run=ld)
    assert r["removed"] and not plist.exists() and not ld.loaded
    # an older macOS: the older command is used
    ld = Launchd(bootstrap_ok=False)
    assert (
        service.install(run=ld)["started"] and ["launchctl", "load", "-w", str(plist)] in ld.asked
    )


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows registry")
def test_on_windows_it_is_in_the_persons_run_list(tmp_path, monkeypatch):
    import winreg

    monkeypatch.setattr(service, "RUN_NAME", "Datas test " + tmp_path.name)
    monkeypatch.setattr(service, "_answers", lambda: True)  # pretend it is already running
    monkeypatch.setattr(service, "_shutdown", lambda: None)
    try:
        r = service.install()
        assert r["started"] and "log in to Windows" in r["notes"][0]
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, service.RUN_KEY) as k:
            line = winreg.QueryValueEx(k, service.RUN_NAME)[0]
        assert "serve --no-browser" in line and "pythonw.exe" in line.lower()
        assert service.status()["installed"]
        assert service.remove()["removed"] and not service.status()["installed"]
    finally:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, service.RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as k:
                winreg.DeleteValue(k, service.RUN_NAME)
        except OSError:
            pass


def test_windows_starts_a_program_with_no_window(monkeypatch, tmp_path):
    monkeypatch.setattr(service.platform, "system", lambda: "Windows")
    monkeypatch.delenv("DATAS_HOME", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "datas-cli.exe"))
    (tmp_path / "Datas.exe").write_text("")
    assert service.command() == [str(tmp_path / "Datas.exe"), "serve", "--no-browser"]
    assert (
        service.run_line([r"C:\Program Files\Datas\Datas.exe", "serve"])
        == '"C:\\Program Files\\Datas\\Datas.exe" serve'
    )


def test_the_window_switch_and_a_phone_cannot_use_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from datas.server import app as server

    asked = []
    monkeypatch.setattr(
        service,
        "status",
        lambda run=None: {"installed": False, "running": False, "at_boot": False, "file": "f"},
    )
    monkeypatch.setattr(
        service,
        "install",
        lambda run=None: (
            asked.append("on")
            or {"started": True, "notes": ["Datas starts when you log in to Windows."]}
        ),
    )
    monkeypatch.setattr(
        service,
        "remove",
        lambda run=None, stop=True: asked.append(("off", stop)) or {"removed": True},
    )
    c = TestClient(server.app, base_url="http://127.0.0.1")
    assert c.get("/api/service").json()["supported"] is True
    server.core.cfg.lang = "es"
    try:
        r = c.post("/api/service", json={"on": True}).json()
        assert r["notes"] == ["Datas arranca cuando iniciás sesión en Windows."]
    finally:
        server.core.cfg.lang = "en"
    c.post("/api/service", json={"on": False})
    assert asked == ["on", ("off", False)]  # off keeps the Datas showing the window running
    assert ("WRITE", "/api/service") in server.REMOTE_REFUSED
