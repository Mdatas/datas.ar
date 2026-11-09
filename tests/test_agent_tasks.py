"""Scheduled agent tasks: due-time arithmetic and the folder grants/tools sandbox."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from datas.agents import tools as T
from datas.agents.folders import resolve_grant
from datas.agents.schedule import Task


def mk(**kw) -> Task:
    base = {"id": "t1", "title": "t", "task": "do", "created": time.time()}
    base.update(kw)
    return Task(**base)


def test_weekly_task_created_after_its_time_waits_for_next_week():
    now = datetime(2026, 11, 9, 17, 30)  # a Monday, 17:30
    t = mk(every="week", at="09:00", weekday="mon", created=now.timestamp())
    assert t.next_due(now) == datetime(2026, 11, 16, 9, 0)
    assert not t.is_due(now)
    t.last_run = datetime(2026, 11, 16, 9, 1).timestamp()
    assert t.next_due(datetime(2026, 11, 16, 9, 5)) == datetime(2026, 11, 23, 9, 0)


def test_daily_task_runs_once_per_day_and_catches_up_after_sleep():
    created = datetime(2026, 11, 9, 8, 0)
    t = mk(every="day", at="09:00", created=created.timestamp())
    assert t.is_due(datetime(2026, 11, 9, 9, 0)) and not t.is_due(datetime(2026, 11, 9, 8, 59))
    t.last_run = datetime(2026, 11, 9, 9, 0).timestamp()
    assert not t.is_due(datetime(2026, 11, 9, 23, 0))
    # computer was off for three days: it is due once at the next start
    assert t.is_due(datetime(2026, 11, 12, 20, 0))


def test_hourly_and_once_and_disabled():
    now = datetime(2026, 11, 9, 10, 0)
    h = mk(every="hour", created=now.timestamp())
    assert h.next_due(now) == now + timedelta(hours=1)
    o = mk(every="once", at="10:30", created=now.timestamp())
    assert o.next_due(now) == datetime(2026, 11, 9, 10, 30)
    o.last_run = now.timestamp()
    assert o.next_due(now) is None
    d = mk(every="day", enabled=False)
    assert d.next_due(now) is None


def test_tools_stay_inside_granted_folders(tmp_path: Path):
    ws = tmp_path / "ws"
    docs = tmp_path / "Documents"
    secret = tmp_path / "secret"
    for d in (ws, docs, secret):
        d.mkdir()
    (docs / "a.txt").write_text("hello")
    (secret / "s.txt").write_text("no")
    ctx = T.ToolContext(workspace=ws, roots=[docs])
    assert "hello" in T.call(ctx, "read_file", {"path": str(docs / "a.txt")})
    assert T.call(ctx, "read_file", {"path": str(secret / "s.txt")}).startswith("DENIED")
    assert T.call(ctx, "read_file", {"path": "../secret/s.txt"}).startswith("DENIED")
    out = T.call(ctx, "move_file", {"source": str(docs / "a.txt"), "destination": "sorted/"})
    assert out.startswith("moved") and (ws / "sorted" / "a.txt").exists()
    out = T.call(ctx, "delete_file", {"path": "sorted/a.txt"})
    assert "trash" in out and list((ws / "_trash").iterdir())
    assert T.call(ctx, "delete_file", {"path": str(docs)}).startswith("refused")
    assert T.call(ctx, "run_command", {"command": "echo hi"}).startswith("DENIED")
    ctx.allow_network = False
    assert T.call(ctx, "web_search", {"query": "x"}).startswith("DENIED")
    names = {s["function"]["name"] for s in T.schemas(ctx)}
    assert "web_search" not in names and "run_command" not in names and "move_file" in names


def test_resolve_grant_refuses_home_and_missing(tmp_path: Path):
    assert resolve_grant(str(tmp_path)) == tmp_path.resolve()
    with pytest.raises(ValueError):
        resolve_grant("~")
    with pytest.raises(ValueError):
        resolve_grant(str(tmp_path / "nope"))
