"""Updates: side by side, tried at once, and back to what worked when something breaks."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import httpx
import pytest

from datas import catalog, updates
from datas.config import Config, runtime_dir
from datas.orchestrator import Datas
from datas.runtime import llamacpp


def test_versions_and_installer_for_each_system(monkeypatch):
    assert updates.version_tuple("v0.10.2") > updates.version_tuple("0.9.9")
    assets = [
        {"name": n, "browser_download_url": "https://example.invalid/" + n, "size": 1}
        for n in (
            "Datas-Setup-0.3.0.exe",
            "Datas-0.3.0-arm64.dmg",
            "datas_0.3.0_amd64.deb",
            "datas-bin-0.3.0-1-x86_64.pkg.tar.zst",
            "datas-0.3.0-linux-x64.tar.gz",
        )
    ]
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    assert updates.asset_for_this_os(assets)["name"].endswith(".exe")
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    assert updates.asset_for_this_os(assets)["name"].endswith(".dmg")
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    real_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda p: (
            str(p) == "/etc/debian_version" or (str(p) != "/etc/arch-release" and real_exists(p))
        ),
    )
    assert updates.asset_for_this_os(assets)["name"].endswith(".deb")
    monkeypatch.setattr(
        Path,
        "exists",
        lambda p: (
            str(p) == "/etc/arch-release" or (str(p) != "/etc/debian_version" and real_exists(p))
        ),
    )
    assert updates.asset_for_this_os(assets)["name"].endswith(".pkg.tar.zst")
    assert updates.asset_for_this_os([]) is None


def test_newer_and_earlier_releases_are_told_apart():
    def handler(request: httpx.Request) -> httpx.Response:
        rels = [
            {"tag_name": "v9.0.0", "assets": [], "html_url": "https://example.invalid/9"},
            {"tag_name": "v9.9.0-beta", "prerelease": True, "assets": []},
            {"tag_name": "v0.0.1", "assets": []},
        ]
        return httpx.Response(200, json=rels)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        info = updates.check_app(c)
    assert info["latest"]["version"] == "9.0.0" and info["latest"]["asset"] is None
    assert [r["version"] for r in info["older"]] == ["0.0.1"]
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as c:
        assert updates.check_app(c)["latest"] is None  # no releases published yet


def test_list_of_ais_updates_beside_the_bundled_one(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    catalog.reload()
    bundled = json.loads(catalog.bundled_path().read_text(encoding="utf-8"))
    newer = dict(bundled, generated="2999-01-01", models=bundled["models"][:3])

    def client(payload) -> httpx.Client:  # noqa: ANN001
        return httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text=json.dumps(payload)))
        )

    try:
        r = updates.update_catalog(client(newer))
        assert r["changed"] and r["source"] == "updated" and r["models"] == 3
        assert json.loads(catalog.bundled_path().read_text(encoding="utf-8")) == bundled
        # an older or equal list changes nothing
        assert not updates.update_catalog(client(bundled))["changed"]
        # a malformed list is refused and the current one stays
        with pytest.raises(ValueError):
            updates.update_catalog(client({"models": [{"id": "x"}]}))
        assert updates.catalog_info()["models"] == 3
        # a damaged update file never breaks the app
        catalog.update_path().write_text("{ not json")
        assert len(catalog.reload().models) == len(bundled["models"])
        back = updates.rollback_catalog()
        assert back["source"] == "bundled" and not catalog.update_path().exists()
    finally:
        monkeypatch.delenv("DATAS_HOME")
        catalog.reload()


def test_settings_are_kept_per_version(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    assert updates.backup_settings("0.2.0") is None  # nothing to keep yet
    c = Config()
    c.lang = "es"
    c.save()
    p = updates.backup_settings("0.2.0")
    assert p and json.loads(p.read_text())["lang"] == "es"
    c.lang = "en"
    c.save()
    updates.backup_settings("0.2.0")  # the first copy of a version is the one that stays
    assert json.loads(p.read_text())["lang"] == "es"


@pytest.mark.skipif(sys.platform == "win32", reason="uses a shell script as a stand-in engine")
def test_an_engine_that_cannot_start_is_rolled_back(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))

    def fake_build(tag: str, works: bool) -> None:
        d = runtime_dir() / tag / "bin"
        d.mkdir(parents=True)
        exe = d / "llama-server"
        exe.write_text(
            "#!/bin/sh\n" + ("echo version: test\n" if works else "echo broken >&2\nexit 3\n")
        )
        exe.chmod(0o755)
        (d.parent / ".datas-ok").write_text(tag + "\n")

    fake_build("b100", True)
    fake_build("b200", True)
    fake_build("b300", False)
    monkeypatch.setattr(
        llamacpp,
        "resolve",
        lambda spec, backend, tag="", client=None: llamacpp.AssetChoice(tag, "x", "http://x", []),
    )
    core = Datas(Config())
    core.cfg.llamacpp_tag = "b100"
    core.cfg.save()
    assert updates.engine_info(core)["tag"] == "b100"
    r = updates.switch_engine(core, "b200")
    assert r == {"tag": "b200", "previous": "b100", "changed": True}
    assert updates.engine_info(core)["previous"] == "b100"
    with pytest.raises(RuntimeError, match="went back to b200"):
        updates.switch_engine(core, "b300")
    assert core.cfg.llamacpp_tag == "b200" and Config.load().llamacpp_tag == "b200"
    assert updates.rollback_engine(core)["tag"] == "b100"
    hist = [(h.get("to"), h["result"]) for h in updates.state()["history"]]
    assert hist == [("b200", "ok"), ("b300", "rolled_back"), ("b100", "ok")]
    with pytest.raises(ValueError):
        updates.switch_engine(core, "../../etc")
    # old builds can be cleared; the active one and the one before it stay
    assert updates.remove_old_engines(core)["removed"] == ["b300"]


def test_only_local_callers_reach_the_api():
    from fastapi.testclient import TestClient

    from datas.server.app import app

    c = TestClient(app)
    assert c.get("/api/privacy").status_code == 200
    # a page that made its own domain point at this device ("DNS rebinding")
    assert c.get("/api/privacy", headers={"Host": "evil.example"}).status_code == 403
    assert c.get("/api/privacy", headers={"Host": "127.0.0.1:8420"}).status_code == 200
    assert c.get("/api/privacy", headers={"Host": "[::1]:8420"}).status_code == 200
    # a stranger's web page trying to change something
    for h in (
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ):
        r = c.post("/api/settings", json={"theme": "night"}, headers=h)
        assert r.status_code == 403, h
    # Datas' own window, and scripts (which send neither header), are fine
    own = {"Origin": "http://127.0.0.1:8420", "Sec-Fetch-Site": "same-origin"}
    assert c.post("/api/settings", json={"theme": "night"}, headers=own).status_code == 200
    assert c.post("/api/settings", json={"theme": "auto"}).json()["theme"] == "auto"
    page = c.get("/")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"


def test_logs_do_not_grow_forever(tmp_path):
    from datas.config import rotate_log

    log = tmp_path / "engine.log"
    log.write_bytes(b"x" * 2000)
    rotate_log(log, max_bytes=1000)
    assert not log.exists() and (tmp_path / "engine.log.1").stat().st_size == 2000
    log.write_bytes(b"y" * 10)
    rotate_log(log, max_bytes=1000)
    assert log.exists()
