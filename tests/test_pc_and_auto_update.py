"""'Configure my PC' tools for the agent, and Datas keeping itself up to date."""

from pathlib import Path

from datas import updates
from datas.agents import pc_tools
from datas.agents import tools as T


def _ctx(tmp_path, **kw):
    return T.ToolContext(workspace=tmp_path / "ws", **kw)


def test_pc_tools_only_with_their_switch(tmp_path):
    names = lambda c: {s["function"]["name"] for s in T.schemas(c)}  # noqa: E731
    assert "change_pc_setting" not in names(_ctx(tmp_path))
    assert {"list_apps", "open_app", "open_settings", "sign_in_by_you"} <= names(
        _ctx(tmp_path, allow_setup=True)
    )
    # without the switch the tool does not exist, even if the AI names it
    assert T.call(_ctx(tmp_path), "pc_settings", {}).startswith("unknown tool")


def test_changes_ask_first_and_can_be_undone(tmp_path, monkeypatch):
    value = {"v": False}
    monkeypatch.setitem(
        pc_tools.SETTINGS,
        "dark_mode",
        {
            "what": "Dark colours",
            pc_tools.SYSTEM: (lambda: value["v"], lambda on: value.update(v=on)),
        },
    )
    asked = []
    ctx = _ctx(tmp_path, allow_setup=True, confirm=lambda text: asked.append(text) or True)
    assert ctx.is_risky("change_pc_setting", {}) and not ctx.is_risky("pc_settings", {})
    out = T.call(ctx, "change_pc_setting", {"name": "dark_mode", "on": True})
    assert value["v"] is True and "was off" in out
    assert asked == ["Turn on: Dark colours"]
    assert "already on" in T.call(ctx, "change_pc_setting", {"name": "dark_mode", "on": "yes"})
    assert "back to off" in T.call(ctx, "undo_pc_changes", {})
    assert value["v"] is False
    assert T.call(ctx, "undo_pc_changes", {}) == "Nothing to undo."
    denied = _ctx(tmp_path, allow_setup=True, confirm=lambda text: False)
    assert T.call(denied, "change_pc_setting", {"name": "dark_mode", "on": True}).startswith(
        "DENIED"
    )
    assert value["v"] is False


def test_sign_in_is_done_by_the_person(tmp_path, monkeypatch):
    monkeypatch.setattr(pc_tools, "_find_app", lambda name: None)
    waits = []
    ctx = _ctx(tmp_path, allow_setup=True, sign_in_wait=lambda text: waits.append(text) or True)
    assert T.call(ctx, "sign_in_by_you", {"app": "Spotify"}) == "The person signed in."
    assert "yourself" in waits[0] and "never sees or types passwords" in waits[0]
    assert "password" in pc_tools.SYSTEM_HINT


def test_apps_are_listed_from_the_system_menus(tmp_path, monkeypatch):
    if pc_tools.SYSTEM != "Linux":
        return
    apps = tmp_path / "home" / ".local/share/applications"
    apps.mkdir(parents=True)
    (apps / "org.example.Notes.desktop").write_text("[Desktop Entry]\nName=Notes\n")
    (apps / "hidden.desktop").write_text("[Desktop Entry]\nName=Hidden\nNoDisplay=true\n")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    names = [a["name"] for a in pc_tools.installed_apps()]
    assert "Notes" in names and "Hidden" not in names
    assert "Notes" in pc_tools.list_apps(None, "not")


def test_unknown_settings_page_is_refused():
    assert pc_tools.open_settings(None, "nonsense").startswith("Unknown page")


def test_auto_update_downloads_a_checked_newer_installer(tmp_path, monkeypatch):
    class Cfg:
        auto_update = True

    class Core:
        cfg = Cfg()

    monkeypatch.setattr(updates, "home", lambda: tmp_path)
    monkeypatch.setattr(updates, "update_catalog", lambda: {"changed": False})
    newer = {
        "version": "99.0.0",
        "page": "p",
        "asset": {"name": "Datas-Setup-99.0.0.exe", "url": "u", "size": 3, "digest": "sha256:ab"},
    }
    monkeypatch.setattr(updates, "check_app", lambda c: {"latest": newer})

    def fake_download(asset, job=None, folder=None):  # noqa: ANN001
        p = folder / asset["name"]
        p.write_bytes(b"exe")
        return p

    monkeypatch.setattr(updates, "download_installer", fake_download)
    out = updates.auto_run(Core())
    assert out["app"] == "99.0.0"
    assert updates.ready()["version"] == "99.0.0"
    assert updates.auto_run(Core()) == {"skipped": "recent"}
    Cfg.auto_update = False
    assert updates.auto_run(Core(), force=True) == {"skipped": "off"}


def test_no_unattended_download_without_a_published_checksum(tmp_path, monkeypatch):
    class Core:
        class cfg:  # noqa: N801
            auto_update = True

    monkeypatch.setattr(updates, "home", lambda: tmp_path)
    monkeypatch.setattr(updates, "update_catalog", lambda: {"changed": False})
    monkeypatch.setattr(
        updates,
        "check_app",
        lambda c: {
            "latest": {"version": "99.0.0", "page": "p", "asset": {"name": "x", "url": "u"}}
        },
    )
    monkeypatch.setattr(updates, "download_installer", lambda *a, **k: 1 / 0)
    updates.auto_run(Core(), force=True)
    assert updates.ready() is None


def test_an_older_or_missing_installer_is_not_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "home", lambda: tmp_path)
    updates._save({"ready": {"version": "0.0.1", "path": str(tmp_path / "old.exe")}})  # noqa: SLF001
    assert updates.ready() is None
    updates._save({"ready": {"version": "99.0.0", "path": str(tmp_path / "gone.exe")}})  # noqa: SLF001
    assert updates.ready() is None
