"""The self-test must pass on a healthy copy, and must notice a missing part."""

import os

from typer.testing import CliRunner

from datas import selftest
from datas.cli import app


def test_a_healthy_copy_passes_and_nothing_of_the_user_is_touched():
    home = os.environ["DATAS_HOME"]
    rows = selftest.run()
    assert [name for name, ok, _ in rows if not ok] == [], rows
    assert len(rows) == 6
    assert os.environ["DATAS_HOME"] == home  # put back as it was


def test_a_missing_part_is_reported_and_the_rest_still_runs(monkeypatch):
    monkeypatch.setattr(selftest, "WINDOW_FILES", (*selftest.WINDOW_FILES, "not-there.js"))
    rows = selftest.run()
    bad = [(name, detail) for name, ok, detail in rows if not ok]
    assert len(bad) == 1 and "not-there.js" in bad[0][1]
    assert len(rows) == 6


def test_the_command_says_so_with_its_exit_code(monkeypatch):
    r = CliRunner().invoke(app, ["selftest"])
    assert r.exit_code == 0 and "everything is in place" in r.output
    monkeypatch.setattr(selftest, "WINDOW_FILES", ("not-there.js",))
    r = CliRunner().invoke(app, ["selftest", "--json"])
    assert r.exit_code == 1 and '"ok": false' in r.output
