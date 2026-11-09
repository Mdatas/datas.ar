"""Scheduled agent tasks: "every Monday at 9, tidy my Downloads". Stored in
``<data>/agent/tasks.json``; results in ``<data>/agent/results/<task>-<time>.md``.

They run while Datas is open (the app has no background service yet — see docs/ROADMAP.md 0.3).
A task missed while the computer was off runs at the next start if it is more than one period
overdue, so a weekly tidy-up still happens. Results are plain files the user asked for, so they
are written in both privacy modes; no chat is kept.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from datas.config import home

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def tasks_file() -> Path:
    d = home() / "agent"
    d.mkdir(parents=True, exist_ok=True)
    return d / "tasks.json"


def results_dir() -> Path:
    d = home() / "agent" / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Task:
    id: str
    title: str
    task: str
    every: str = "day"  # day | week | hour | once
    at: str = "09:00"  # HH:MM local, for day/week
    weekday: str = "mon"  # for week
    folders: list[str] = field(default_factory=list)
    internet: bool = True
    allow_shell: bool = False
    enabled: bool = True
    created: float = field(default_factory=time.time)
    last_run: float | None = None
    last_state: str = ""  # done | error | running
    last_summary: str = ""
    last_result: str = ""  # path of the result file

    def next_due(self, now: datetime | None = None) -> datetime | None:
        now = now or datetime.now()
        if not self.enabled:
            return None
        if self.every == "hour":
            return datetime.fromtimestamp(self.last_run or self.created) + timedelta(hours=1)
        hh, mm = (int(x) for x in self.at.split(":"))
        if self.every == "once":
            if self.last_run:
                return None
            due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            return due if due > now else due + timedelta(days=1)
        # a task never runs for a moment that was already past when it was created
        last = datetime.fromtimestamp(self.last_run or self.created)
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if self.every == "week":
            target = WEEKDAYS.index(self.weekday) if self.weekday in WEEKDAYS else 0
            due = due - timedelta(days=(due.weekday() - target) % 7)
            while due <= last:
                due += timedelta(days=7)
            return due
        # day
        while due <= last:
            due += timedelta(days=1)
        return due

    def is_due(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        due = self.next_due(now)
        return bool(due and due <= now)


class Scheduler:
    """One background thread; checks every 30 s; runs one task at a time."""

    def __init__(self, runner) -> None:  # noqa: ANN001 - callable(Task) -> (state, summary, path)
        self.runner = runner
        self.tasks: list[Task] = self.load()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.running_id: str | None = None

    # ---- persistence ---------------------------------------------------------
    @staticmethod
    def load() -> list[Task]:
        f = tasks_file()
        if not f.exists():
            return []
        try:
            return [Task(**t) for t in json.loads(f.read_text(encoding="utf-8"))]
        except (ValueError, TypeError):
            return []

    def save(self) -> None:
        tasks_file().write_text(
            json.dumps([asdict(t) for t in self.tasks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ---- CRUD ------------------------------------------------------------------
    def add(self, **fields) -> Task:
        t = Task(id=uuid.uuid4().hex[:8], **fields)
        with self._lock:
            self.tasks.append(t)
            self.save()
        return t

    def update(self, task_id: str, **fields) -> Task | None:
        with self._lock:
            for t in self.tasks:
                if t.id == task_id:
                    for k, v in fields.items():
                        if hasattr(t, k) and v is not None:
                            setattr(t, k, v)
                    self.save()
                    return t
        return None

    def remove(self, task_id: str) -> bool:
        with self._lock:
            n = len(self.tasks)
            self.tasks = [t for t in self.tasks if t.id != task_id]
            self.save()
            return len(self.tasks) < n

    def get(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    # ---- running -----------------------------------------------------------------
    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="datas-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_now(self, task_id: str) -> bool:
        t = self.get(task_id)
        if not t or self.running_id:
            return False
        threading.Thread(target=self._run, args=(t,), daemon=True).start()
        return True

    def _loop(self) -> None:
        time.sleep(20)  # let the AI start first
        while not self._stop.is_set():
            try:
                due = [t for t in self.tasks if t.is_due()]
                if due and not self.running_id:
                    self._run(due[0])
            except Exception:  # noqa: BLE001 - the loop must survive anything
                pass
            self._stop.wait(30)

    def _run(self, t: Task) -> None:
        self.running_id = t.id
        t.last_state = "running"
        t.last_run = time.time()
        self.save()
        try:
            state, summary, path = self.runner(t)
        except Exception as e:  # noqa: BLE001
            state, summary, path = "error", f"{type(e).__name__}: {e}", ""
        t.last_state, t.last_summary, t.last_result = state, summary[:2000], path
        self.save()
        self.running_id = None
