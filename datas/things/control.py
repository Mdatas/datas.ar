"""The mouse and the keyboard, moved by the agent — experimental, off unless switched on.

Why it is separate and guarded: a click cannot be undone, the AI sees the whole screen, and
the small AIs that fit a normal computer make mistakes when they have to find a button in a
picture. So: its own switch in the agent window, every action asks first unless the person
chose otherwise, moving the mouse into a corner of the screen stops it at once, and it is
never available from a linked phone or to a task that runs by itself.

Uses PyAutoGUI. Works on Windows, macOS (needs Accessibility permission) and Linux with X11;
not on Wayland.
"""

from __future__ import annotations

import os
import platform

from datas.things import ThingError
from datas.words import Said, tr

ACTIONS = ("move", "click", "double_click", "right_click", "type", "key", "scroll")
MAX_TEXT = 2000


def available() -> dict:
    """{"ok": bool, "why": str} — without touching anything."""
    if platform.system() == "Linux":
        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
            return {
                "ok": False,
                "why": "this session uses Wayland; mouse and keyboard control needs X11",
            }
        if not os.environ.get("DISPLAY"):
            return {"ok": False, "why": "there is no screen session"}
    try:
        import importlib.util

        if importlib.util.find_spec("pyautogui") is None:
            return {
                "ok": False,
                "why": "the mouse and keyboard part (PyAutoGUI) is not in this copy",
            }
    except (ImportError, ValueError):
        return {"ok": False, "why": "the mouse and keyboard part (PyAutoGUI) is not in this copy"}
    return {"ok": True, "why": ""}


def _gui():  # noqa: ANN202
    ok = available()
    if not ok["ok"]:
        raise ThingError("Mouse and keyboard control is not available: {why}.", why=ok["why"])
    try:
        import pyautogui
    except Exception as e:  # noqa: BLE001 - no display, missing system library
        raise ThingError("Mouse and keyboard control could not start: {why}", why=str(e)) from e
    pyautogui.FAILSAFE = True  # the mouse in a corner of the screen stops everything
    pyautogui.PAUSE = 0.25
    return pyautogui


def describe(
    action: str,
    x: int | None = None,
    y: int | None = None,
    text: str | None = None,
    keys: str | None = None,
    amount: int | None = None,
    lang: str = "en",
) -> str:
    """What an action will do, in words, for the question shown to the person."""
    if action in ("click", "double_click", "right_click", "move"):
        sentence = {
            "click": "Click at ({x}, {y})",
            "double_click": "Double-click at ({x}, {y})",
            "right_click": "Right-click at ({x}, {y})",
            "move": "Move the mouse to ({x}, {y})",
        }[action]
        return tr(sentence, lang, x=x, y=y)
    if action == "type":
        return tr("Type: {text}", lang, text=repr(str(text or "")[:200]))
    if action == "key":
        return tr("Press {keys}", lang, keys=keys)
    if action == "scroll":
        up = (amount or 0) > 0
        return tr("Scroll up {n}" if up else "Scroll down {n}", lang, n=abs(amount or 0))
    return action


class _Described:
    """An action in words, said in whichever language is asked for (see ``describe``)."""

    def __init__(self, *what) -> None:  # noqa: ANN002
        self.what = what

    def say(self, lang: str = "en") -> str:
        return describe(*self.what, lang=lang)


def to_screen(x: int, y: int, picture: tuple[int, int], screen: tuple[int, int]) -> tuple[int, int]:
    """A place in a picture of the screen → the same place in the mouse's own positions.
    The picture is usually smaller than the screen, and on a Mac with a Retina screen the
    mouse counts half as many dots as the picture has."""
    pw, ph = picture
    sw, sh = screen
    if pw <= 0 or ph <= 0:
        return int(x), int(y)
    return (
        min(sw - 1, max(0, round(int(x) * sw / pw))),
        min(sh - 1, max(0, round(int(y) * sh / ph))),
    )


def act(
    action: str,
    x: int | None = None,
    y: int | None = None,
    text: str | None = None,
    keys: str | None = None,
    amount: int | None = None,
    gui=None,  # noqa: ANN001
    picture: tuple[int, int] | None = None,
) -> str:
    """Do one thing with the mouse or keyboard. ``picture`` is the size of the picture of the
    screen that x and y were read from (see ``to_screen``); without it they are the mouse's
    own positions. ``gui`` replaces PyAutoGUI in the tests."""
    if action not in ACTIONS:
        raise ThingError("action is one of: {actions}", actions=", ".join(ACTIONS))
    g = gui or _gui()
    try:
        if action in ("move", "click", "double_click", "right_click"):
            if x is None or y is None:
                raise ThingError("That needs a place on the screen: x and y.")
            w, h = g.size()
            x, y = int(x), int(y)
            limit_w, limit_h = picture or (w, h)
            if not (0 <= x < limit_w and 0 <= y < limit_h):
                raise ThingError(
                    "({x}, {y}) is outside the picture of the screen, which is {w} by {h}.",
                    x=x,
                    y=y,
                    w=limit_w,
                    h=limit_h,
                )
            px, py = to_screen(x, y, picture, (w, h)) if picture else (x, y)
            if action == "move":
                g.moveTo(px, py, duration=0.2)
            elif action == "click":
                g.click(px, py)
            elif action == "double_click":
                g.doubleClick(px, py)
            else:
                g.click(px, py, button="right")
        elif action == "type":
            if not text:
                raise ThingError("Nothing to type.")
            g.write(str(text)[:MAX_TEXT], interval=0.01)
        elif action == "key":
            names = [
                k.strip().lower() for k in str(keys or "").replace("-", "+").split("+") if k.strip()
            ]
            if not names:
                raise ThingError('Name the key, for example "enter" or "ctrl+s".')
            g.hotkey(*names)
        else:
            g.scroll(int(amount or 0))
    except ThingError:
        raise
    except Exception as e:  # noqa: BLE001 - PyAutoGUI's FailSafeException and system errors
        if type(e).__name__ == "FailSafeException":
            raise ThingError("Stopped: the mouse was moved into a corner of the screen.") from e
        raise ThingError("The system did not allow that: {why}", why=str(e)) from e
    return Said("Done: {what}", what=_Described(action, x, y, text, keys, amount))
