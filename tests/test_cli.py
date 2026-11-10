from typer.testing import CliRunner

from datas.cli import app
from datas.config import Config

run = CliRunner().invoke


def test_showing_the_hand_listed_workers_does_not_clear_them():
    assert "10.0.0.5:50052" in run(app, ["pool", "nodes", "--set", "10.0.0.5:50052"]).output
    assert "10.0.0.5:50052" in run(app, ["pool", "nodes"]).output  # only looking
    assert Config.load().pool_nodes == "10.0.0.5:50052"
    assert "(none)" in run(app, ["pool", "nodes", "--set", ""]).output
    assert Config.load().pool_nodes == ""


def test_version_and_help_work():
    from datas import __version__

    assert __version__ in run(app, ["--version"]).output
    out = run(app, ["--help"]).output
    assert "selftest" in out and "link" in out


def test_run_starts_the_ai_in_a_datas_that_is_already_open(monkeypatch):
    """With the window or the background service running, `datas run` must not start a
    second engine next to it: it asks the running Datas and follows the job."""
    import datas.cli as cli

    calls, states = (
        [],
        [
            {"state": "running", "phase": "model", "percent": 40.0},
            {"state": "done", "phase": "start"},
        ],
    )

    def fake_api(method, path, **kw):
        calls.append((method, path, kw.get("json") or kw.get("params")))
        if path == "/api/recommend":
            return {"default": {"model_id": "qwen3-4b", "quant": "Q4_K_M"}, "fits": []}
        if path == "/api/run":
            return {"id": "j1"}
        return states.pop(0)

    monkeypatch.setattr(cli, "_datas_is_open", lambda: True)
    monkeypatch.setattr(cli, "_app_api", fake_api)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        cli, "_core", lambda: (_ for _ in ()).throw(AssertionError("started its own engine"))
    )
    r = run(app, ["run"])
    assert r.exit_code == 0, r.output
    assert (
        "already running on this device" in r.output
        and "Ready." in r.output
        and "model 40%" in r.output
    )
    sent = next(body for method, path, body in calls if path == "/api/run")
    assert sent["model_id"] == "qwen3-4b" and sent["quant"] == "Q4_K_M" and sent["starter"] is False
    # a failure there is reported here
    states[:] = [{"state": "error", "error": "not enough disk space"}]
    r = run(app, ["run", "qwen3-4b", "--quant", "Q4_K_M"])
    assert r.exit_code == 1 and "not enough disk space" in r.output


def test_the_new_commands_are_there():
    out = run(app, ["--help"]).output
    assert "things" in out and "service" in out
    assert "photo" in run(app, ["things", "--help"]).output
    r = run(app, ["things", "list"])
    assert r.exit_code == 0 and "Cameras:" in r.output and "Mouse and keyboard" in r.output
    assert "install" in run(app, ["service", "--help"]).output


def test_a_computer_without_a_screen_lets_another_open_its_datas(monkeypatch):
    """`datas-cli link window "Laptop" on` at the small computer; `link open "Pi"` at the
    laptop. Both go through the Datas that is running, by the name the person knows."""
    import datas.cli as cli

    peers = [
        {"id": "ab12" * 16, "name": "Laptop", "window": False},
        {"id": "cd34" * 16, "name": "Pi", "window": False},
    ]
    calls = []

    def fake_api(method, path, **kw):
        calls.append((method, path, kw.get("json")))
        if path == "/api/link":
            return {"peers": peers}
        if path.endswith("/open"):
            return {"url": "http://127.0.0.1:50123/", "name": "Pi", "shown": kw["json"]["show"]}
        return {"name": "Laptop", "window": kw["json"]["window"]}

    monkeypatch.setattr(cli, "_app_api", fake_api)
    r = run(app, ["link", "window", "laptop", "on"])
    assert r.exit_code == 0 and "Laptop may open the Datas of this computer." in r.output
    assert calls[-1] == ("POST", f"/api/link/peers/{'ab12' * 16}", {"window": True})
    r = run(app, ["link", "window", "Laptop", "off"])
    assert "may no longer open" in r.output and calls[-1][2] == {"window": False}
    assert run(app, ["link", "window", "Laptop", "maybe"]).exit_code != 0
    r = run(app, ["link", "window", "Nobody", "on"])
    assert r.exit_code == 1 and '"Laptop", "Pi"' in r.output  # says which names exist

    r = run(app, ["link", "open", "Pi", "--no-window"])
    assert r.exit_code == 0 and "http://127.0.0.1:50123/" in r.output
    assert calls[-1] == ("POST", f"/api/link/peers/{'cd34' * 16}/open", {"show": False})
    r = run(app, ["link", "open", "cd34"])  # the start of its id works too
    assert "is open in its own window" in r.output and calls[-1][2] == {"show": True}


def test_every_file_that_states_the_version_states_the_same_one():
    """The version is written in a few places a build reads by itself (the Arch package
    recipe, the Windows installer script, the phone apps). One left behind breaks a build."""
    import re
    from pathlib import Path

    from datas import __version__

    root = Path(__file__).resolve().parents[1]
    places = {
        "pyproject.toml": r'(?m)^version = "(.+?)"',
        "installer/linux/arch/PKGBUILD": r"(?m)^pkgver=(\S+)",
        "installer/windows/datas.iss": r'#define AppVersion "(.+?)"',
        "android/app/build.gradle.kts": r'versionName = "(.+?)"',
        "ios/App/project.yml": r'MARKETING_VERSION: "(.+?)"',
    }
    found = {}
    for name, pattern in places.items():
        text = (root / name).read_text(encoding="utf-8")
        m = re.search(pattern, text)
        found[name] = m.group(1) if m else None
    assert found == dict.fromkeys(places, __version__)
