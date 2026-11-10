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
