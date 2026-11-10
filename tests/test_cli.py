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
