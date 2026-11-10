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
    assert 'Environment="DATAS_HOME=/srv/datas data"\n' in service.unit_text(["x"])
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
    monkeypatch.setattr(service.platform, "system", lambda: "Windows")
    with pytest.raises(Problem) as e:
        service.install()
    assert "only available on Linux" in str(
        e.value
    ) and "solo está disponible en Linux" in e.value.say("es")
    monkeypatch.setattr(service.platform, "system", lambda: "Linux")
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    with pytest.raises(Problem) as e:
        service.status()
    assert "no systemd" in str(e.value)
