"""Hardware around this computer and on the user's own network — "things".

Cameras, the screen, printers, boards on a serial port (Arduino, ESP32, 3D printers,
instruments), and devices that speak the common open protocols of home and industrial
automation: MQTT, Home Assistant, Modbus. The mouse and keyboard are in ``control``.

Nothing here runs by itself. It is used when the person asks — "a photo from the camera" in a
chat — or by the agent when its switch *May use my camera, screen, printer and other
hardware* is on. Looking and listing are free; anything that acts on the world (print a
page, write to a board, switch a light, move the mouse) asks first. From a linked phone all
of it is refused (see ``REMOTE_REFUSED`` in datas/server/app.py): a phone must not be a way
to look through the computer's camera.

``local``   things plugged into this computer
``net``     things on the network
``control`` the mouse and keyboard (experimental)
See docs/HARDWARE.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from datas.config import home
from datas.words import Problem, tr


class ThingError(Problem):
    """Something to tell the person in plain words: no camera, printer offline, wrong address.
    ``ThingError("There is no printer called {name}.", name=x)`` — the sentence is kept apart
    from its values so the window can say it in the person's language (datas.words)."""


# ---------------------------------------------------------------------------
# settings for the things that need an address or a password: <home>/things.json
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "mqtt": {"host": "", "port": 1883, "username": "", "password": "", "tls": False},
    "home_assistant": {"url": "", "token": ""},
    "modbus": [],  # [{"name": "inverter", "host": "192.168.1.50", "port": 502, "unit": 1}]
}
SECRETS = (("mqtt", "password"), ("home_assistant", "token"))


def settings_path() -> Path:
    return home() / "things.json"


def settings() -> dict:
    out = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if isinstance(saved, dict):
        for key in ("mqtt", "home_assistant"):
            if isinstance(saved.get(key), dict):
                out[key].update({k: v for k, v in saved[key].items() if k in DEFAULTS[key]})
        if isinstance(saved.get("modbus"), list):
            out["modbus"] = [m for m in (_modbus_entry(x) for x in saved["modbus"]) if m]
    return out


def _modbus_entry(x) -> dict | None:  # noqa: ANN001
    if not isinstance(x, dict) or not str(x.get("host", "")).strip():
        return None
    try:
        return {
            "name": " ".join(str(x.get("name") or x["host"]).split())[:40],
            "host": str(x["host"]).strip(),
            "port": int(x.get("port") or 502),
            "unit": int(x.get("unit") or 1),
        }
    except (TypeError, ValueError):
        return None


def save_settings(new: dict) -> dict:
    """Merge ``new`` into the saved settings. An empty password or token keeps the old one;
    the word "-" removes it, and so does saving the connection with an empty address."""
    cur = settings()
    for key in ("mqtt", "home_assistant"):
        for k, v in (new.get(key) or {}).items():
            if k not in DEFAULTS[key]:
                continue
            if (key, k) in SECRETS:
                if v in (None, ""):
                    continue
                v = "" if v == "-" else str(v)
            cur[key][k] = type(DEFAULTS[key][k])(v) if v is not None else DEFAULTS[key][k]
    if isinstance(new.get("modbus"), list):
        cur["modbus"] = [m for m in (_modbus_entry(x) for x in new["modbus"]) if m][:30]
    # a connection without an address has no use for its secret: emptying the address forgets it
    if not cur["mqtt"]["host"].strip():
        cur["mqtt"]["username"] = cur["mqtt"]["password"] = ""
    if not cur["home_assistant"]["url"].strip():
        cur["home_assistant"]["token"] = ""
    p = settings_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)  # it can hold a password and an access token
    except OSError:
        pass
    tmp.replace(p)
    return public_settings()


def public_settings() -> dict:
    """The settings as the window may show them: secrets become "is one set?"."""
    s = settings()
    for key, k in SECRETS:
        s[key][k + "_set"] = bool(s[key].pop(k))
    return s


# ---------------------------------------------------------------------------
# what is there
# ---------------------------------------------------------------------------


def inventory(lang: str = "en") -> dict:
    """What is plugged into this computer, in plain shapes for the window and the agent.
    Never raises: a part that cannot be listed comes back empty with a reason. The words a
    person reads (what a board is, why something is missing) come in ``lang``."""
    from datas.things import control, local

    out: dict = {"problems": {}}
    for key, fn in (
        ("cameras", local.cameras),
        ("printers", local.printers),
        ("serial", local.serial_ports),
        ("screens", local.screens),
    ):
        try:
            out[key] = fn()
        except Exception as e:  # noqa: BLE001 - one missing tool must not hide the rest
            out[key] = []
            said = e.say(lang) if isinstance(e, Problem) else str(e)
            out["problems"][key] = said or type(e).__name__
    for p in out["serial"]:
        p["what"] = tr(p["what"], lang)
    ctl = control.available()
    out["control"] = {"ok": ctl["ok"], "why": tr(ctl["why"], lang) if ctl["why"] else ""}
    out["ffmpeg"] = ffmpeg_state()
    s = public_settings()
    out["connections"] = {
        "mqtt": bool(s["mqtt"]["host"]),
        "home_assistant": bool(s["home_assistant"]["url"]),
        "modbus": [m["name"] for m in s["modbus"]],
    }
    return out


def ffmpeg_state() -> dict:
    """Is FFmpeg (which reads the camera) here, and how big is the download if it is not."""
    from datas import programs

    dl = programs.ffmpeg_download()
    return {"found": bool(programs.ffmpeg()), "bytes": dl["bytes"] if dl else None}


def describe(inv: dict | None = None) -> str:
    """The same, as a few lines of text for the agent."""
    inv = inv or inventory()
    lines = []
    cams = inv.get("cameras") or []
    lines.append(
        "Cameras: " + (", ".join(f"{c['id']} ({c['name']})" for c in cams) or "none found")
    )
    scr = inv.get("screens") or []
    lines.append(
        "Screens: " + (", ".join(f"{s['width']}x{s['height']}" for s in scr) or "none found")
    )
    pr = inv.get("printers") or []
    lines.append(
        "Printers: "
        + (
            ", ".join(p["name"] + (" (default)" if p.get("default") else "") for p in pr)
            or "none found"
        )
    )
    ser = inv.get("serial") or []
    lines.append(
        "Serial ports (boards, instruments): "
        + (", ".join(f"{p['port']} — {p['what']}" for p in ser) or "none found")
    )
    con = inv.get("connections") or {}
    lines.append(
        "Connections set up by the user: "
        + (
            ", ".join(
                [
                    n
                    for n, on in (
                        ("MQTT", con.get("mqtt")),
                        ("Home Assistant", con.get("home_assistant")),
                    )
                    if on
                ]
                + [f"Modbus device '{n}'" for n in con.get("modbus") or []]
            )
            or "none"
        )
    )
    ctl = inv.get("control") or {}
    lines.append(
        "Mouse and keyboard control: "
        + ("possible" if ctl.get("ok") else f"not available ({ctl.get('why', '')})")
    )
    for part, why in (inv.get("problems") or {}).items():
        lines.append(f"({part} could not be listed: {why})")
    return "\n".join(lines)
