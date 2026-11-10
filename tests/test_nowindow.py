"""Windows: what Datas starts gets no console window (datas/nowindow.py)."""

import subprocess
import sys

import pytest

from datas import nowindow


def test_a_child_gets_no_window_only_when_there_is_no_console_to_share():
    assert nowindow.flags_for(0, has_console=False) == nowindow.NO_WINDOW
    assert nowindow.flags_for(0, has_console=True) == 0  # datas-cli in a terminal: unchanged
    # asked for its own console, or detached on purpose: left as asked
    assert nowindow.flags_for(nowindow.NEW_CONSOLE, False) == nowindow.NEW_CONSOLE
    assert nowindow.flags_for(nowindow.DETACHED, False) == nowindow.DETACHED
    assert nowindow.flags_for(0x200, False) == 0x200 | nowindow.NO_WINDOW


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_on_windows_every_start_goes_through_it(monkeypatch):
    monkeypatch.setattr(nowindow, "_has_console", lambda: False)
    seen = []
    import _winapi

    real = _winapi.CreateProcess

    def spy(*a):
        seen.append(a[5])  # creationflags
        return real(*a)

    monkeypatch.setattr(_winapi, "CreateProcess", spy)
    subprocess.run(["cmd", "/c", "exit 0"], capture_output=True)
    assert seen and seen[0] & nowindow.NO_WINDOW
