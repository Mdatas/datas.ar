"""The agent's tools for hardware and devices on the network (see datas/things).

Offered only when the person switched on *May use my camera, screen, printer and other
hardware* for the session
(``ctx.allow_things``); the mouse and keyboard need their own switch (``ctx.allow_control``).
Looking and listing run freely; whatever acts on the world, or looks through the camera or
at the screen, is "risky": it asks first unless the person chose never to be asked.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from datas import things
from datas.things import ThingError, control, local, net

# tools that act on the world or look at the person's surroundings: they ask first
ACTS = {
    "take_photo",
    "look_at_screen",
    "print_file",
    "serial_send",
    "mqtt_publish",
    "home_do",
    "modbus_write",
    "mouse_keyboard",
}

NEEDS_SWITCH = (
    "DENIED: using cameras, printers, boards and other devices needs the switch 'May use my "
    "camera, screen, printer and other hardware' in the agent window."
)
NEEDS_CONTROL = (
    "DENIED: moving the mouse and typing needs 'May use the mouse and keyboard' switched on in "
    "the agent window."
)


def _picture(ctx, data: bytes, kind: str, save_as: str | None) -> str:  # noqa: ANN001
    """Keep a picture in the agent's folder and, if the AI can see, hand it over to look at."""
    name = save_as or f"{kind}s/{kind}-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    if not name.lower().endswith((".jpg", ".jpeg")):
        name += ".jpg"
    path = ctx.inside(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if ctx.vision:
        ctx.images.append({"name": path.name, "jpeg": data})
        return f"saved {path} — the picture follows, look at it."
    return (
        f"saved {path}. The AI that is running cannot see pictures, so you cannot look at it "
        "yourself; tell the user where it is. (An AI that understands pictures can be added "
        "in Add an AI.)"
    )


def list_devices(ctx) -> str:  # noqa: ANN001
    return things.describe()


def network_devices(ctx, seconds: float = 3.0) -> str:  # noqa: ANN001
    found = net.around(seconds)
    if not found:
        return "No device announced itself on this network."
    return "\n".join(
        f"- {d['address']}: {d['name'] or d.get('host') or '?'} — {d['kind']}"
        + (f", port {d['port']}" if d.get("port") else "")
        for d in found[:80]
    )


def take_photo(ctx, camera: str | None = None, save_as: str | None = None) -> str:  # noqa: ANN001
    # FFmpeg (which reads the camera) is fetched once if it is missing and the agent may use
    # the internet; otherwise the answer says where the person can get it
    return _picture(ctx, local.photo(camera, fetch=ctx.allow_network), "photo", save_as)


def look_at_screen(ctx, save_as: str | None = None) -> str:  # noqa: ANN001
    # with the mouse and keyboard on, only the main screen: that is where clicks land
    data = local.screenshot(all_screens=not ctx.allow_control)
    w, h = local.picture_size(data)
    ctx.screen_picture = (w, h)
    said = _picture(ctx, data, "screen", save_as)
    if ctx.allow_control:
        said += (
            f" The picture is {w} by {h}; for mouse_keyboard give x and y as places in this "
            "picture (0, 0 is its top left corner)."
        )
    return said


def print_file(ctx, path: str, printer: str | None = None, copies: int = 1) -> str:  # noqa: ANN001
    return local.print_file(ctx.inside(path), printer, copies)


def serial_send(ctx, port: str, text: str, baud: int = 9600, seconds: float = 2.0) -> str:  # noqa: ANN001
    said = local.serial_talk(port, text, seconds, baud)
    return (
        "the device answered:\n" + said if said.strip() else "sent; the device said nothing back."
    )


def serial_read(ctx, port: str, seconds: float = 3.0, baud: int = 9600) -> str:  # noqa: ANN001
    said = local.serial_talk(port, None, seconds, baud)
    return said if said.strip() else f"nothing arrived on {port} in {seconds} seconds."


def mqtt_publish(ctx, topic: str, message: str, retain: bool = False) -> str:  # noqa: ANN001
    return net.mqtt_publish(topic, str(message), retain)


def mqtt_read(ctx, topic: str = "#", seconds: float = 5.0) -> str:  # noqa: ANN001
    got = net.mqtt_read(topic, seconds)
    if not got:
        return f"no message arrived on {topic} in {seconds} seconds."
    return "\n".join(f"{m['topic']}: {m['message']}" for m in got)


def home_list(ctx, domain: str | None = None) -> str:  # noqa: ANN001
    states = net.home_states(domain)
    if not states:
        return "Home Assistant has nothing of that kind."
    more = (
        f"\n… and {len(states) - 200} more; ask for one kind (light, switch, sensor…)."
        if len(states) > 200
        else ""
    )
    return (
        "\n".join(
            f"{s['id']} = {s['state']}" + (f"  ({s['name']})" if s["name"] else "")
            for s in states[:200]
        )
        + more
    )


def home_do(ctx, service: str, entity: str | None = None, data: dict | None = None) -> str:  # noqa: ANN001
    return net.home_call(service, entity, data)


def modbus_read(ctx, device: str, kind: str, address: int, count: int = 1) -> str:  # noqa: ANN001
    vals = net.modbus_read(net.modbus_device(device), kind, address, count)
    return ", ".join(f"{int(address) + i}: {v}" for i, v in enumerate(vals))


def modbus_write(ctx, device: str, kind: str, address: int, values: list[int]) -> str:  # noqa: ANN001
    if not isinstance(values, list):
        values = [values]
    return net.modbus_write(net.modbus_device(device), kind, address, values)


def mouse_keyboard(  # noqa: ANN001
    ctx,
    action: str,
    x: int | None = None,
    y: int | None = None,
    text: str | None = None,
    keys: str | None = None,
    amount: int | None = None,
) -> str:
    if not ctx.allow_control:
        return NEEDS_CONTROL
    if action in ("move", "click", "double_click", "right_click") and not ctx.screen_picture:
        return "Look at the screen first (look_at_screen), then give x and y from that picture."
    return control.act(action, x, y, text, keys, amount, picture=ctx.screen_picture)


def _schema(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


S, N, B = {"type": "string"}, {"type": "number"}, {"type": "boolean"}
INT = {"type": "integer"}

TOOLS: dict[str, tuple[Callable[..., str], dict]] = {
    "list_devices": (
        list_devices,
        _schema(
            "list_devices",
            "What is plugged into this computer (cameras, screens, printers, serial ports with boards such as Arduino) and which connections the user set up (MQTT, Home Assistant, Modbus devices).",
            {},
            [],
        ),
    ),
    "network_devices": (
        network_devices,
        _schema(
            "network_devices",
            "Devices on the user's network that announce themselves: printers, NAS, Raspberry Pi and other computers, smart-home devices, cameras. Nothing is probed.",
            {"seconds": N},
            [],
        ),
    ),
    "take_photo": (
        take_photo,
        _schema(
            "take_photo",
            "Take one picture with a camera of this computer and save it as JPEG in your workspace. If you can see pictures, you receive it.",
            {"camera": S, "save_as": S},
            [],
        ),
    ),
    "look_at_screen": (
        look_at_screen,
        _schema(
            "look_at_screen",
            "Take a picture of what is on the user's screen right now and save it. If you can see pictures, you receive it.",
            {"save_as": S},
            [],
        ),
    ),
    "print_file": (
        print_file,
        _schema(
            "print_file",
            "Print a file from the allowed folders on paper (PDF, text and pictures directly; Word, Excel and PowerPoint through LibreOffice).",
            {"path": S, "printer": S, "copies": INT},
            ["path"],
        ),
    ),
    "serial_send": (
        serial_send,
        _schema(
            "serial_send",
            "Write one line of text to a board or instrument on a serial port (Arduino, ESP32, 3D printer…) and return what it answers. baud is the speed set in the board's program: Arduino examples use 9600, ESP32 and MicroPython 115200.",
            {"port": S, "text": S, "baud": INT, "seconds": N},
            ["port", "text"],
        ),
    ),
    "serial_read": (
        serial_read,
        _schema(
            "serial_read",
            "Listen to a serial port for some seconds and return what the board or instrument says (sensor readings, log lines).",
            {"port": S, "seconds": N, "baud": INT},
            ["port"],
        ),
    ),
    "mqtt_publish": (
        mqtt_publish,
        _schema(
            "mqtt_publish",
            "Send a message to one MQTT topic through the user's broker (smart plugs, lights, Zigbee2MQTT, Tasmota, ESPHome, robots).",
            {"topic": S, "message": S, "retain": B},
            ["topic", "message"],
        ),
    ),
    "mqtt_read": (
        mqtt_read,
        _schema(
            "mqtt_read",
            "Read the messages arriving on an MQTT topic for some seconds. '#' and '+' stand for any topic part, e.g. 'home/+/temperature'.",
            {"topic": S, "seconds": N},
            [],
        ),
    ),
    "home_list": (
        home_list,
        _schema(
            "home_list",
            "List what the user's Home Assistant knows and each thing's state. domain narrows it: light, switch, sensor, climate, cover, lock, media_player…",
            {"domain": S},
            [],
        ),
    ),
    "home_do": (
        home_do,
        _schema(
            "home_do",
            "Ask Home Assistant to do something, e.g. service 'light.turn_on' with entity 'light.kitchen' and data {'brightness': 120}; 'switch.toggle'; 'climate.set_temperature'; 'scene.turn_on'.",
            {"service": S, "entity": S, "data": {"type": "object"}},
            ["service"],
        ),
    ),
    "modbus_read": (
        modbus_read,
        _schema(
            "modbus_read",
            "Read values from an industrial device the user set up (PLC, inverter, meter) over Modbus (network or serial cable). kind: holding or input (numbers 0–65535), coil or discrete (1/0).",
            {"device": S, "kind": S, "address": INT, "count": INT},
            ["device", "kind", "address"],
        ),
    ),
    "modbus_write": (
        modbus_write,
        _schema(
            "modbus_write",
            "Write values to an industrial device over Modbus (network or serial cable). kind: holding (numbers) or coil (1/0). This changes how a machine behaves: be sure of the address.",
            {"device": S, "kind": S, "address": INT, "values": {"type": "array", "items": INT}},
            ["device", "kind", "address", "values"],
        ),
    ),
    "mouse_keyboard": (
        mouse_keyboard,
        _schema(
            "mouse_keyboard",
            "Use the mouse or keyboard of this computer (experimental). action: move, click, double_click, right_click (need x and y: a place in the last picture from look_at_screen), type (text), key (keys such as 'enter' or 'ctrl+s'), scroll (amount, positive is up). One small step at a time, then look at the screen again.",
            {"action": S, "x": INT, "y": INT, "text": S, "keys": S, "amount": INT},
            ["action"],
        ),
    ),
}


def schemas(ctx) -> list[dict]:  # noqa: ANN001
    if not ctx.allow_things:
        return []
    return [s for name, (_, s) in TOOLS.items() if name != "mouse_keyboard" or ctx.allow_control]


def run(ctx, name: str, args: dict) -> str:  # noqa: ANN001
    """Call a device tool. Problems come back as a sentence the AI can pass on."""
    if not ctx.allow_things:
        return NEEDS_SWITCH
    try:
        return TOOLS[name][0](ctx, **args)
    except ThingError as e:
        return f"could not: {e}"


def confirm_text(name: str, args: dict, lang: str = "en") -> str | None:
    """The question shown to the person before a device is used, in plain words and in
    their language (None: fall back to the tool's name and raw arguments)."""
    from datas.words import tr

    a = {k: (str(v)[:200] if isinstance(v, str) else v) for k, v in args.items()}
    try:
        if name == "mouse_keyboard":
            what = control.describe(
                str(a.get("action")), a.get("x"), a.get("y"), a.get("text"), a.get("keys"),
                a.get("amount"), lang=lang,
            )  # fmt: skip
            return tr("Mouse and keyboard — {what}", lang, what=what)
        if name == "take_photo":
            if a.get("camera"):
                return tr("Take a picture with the camera {camera}", lang, camera=a["camera"])
            return tr("Take a picture with the camera", lang)
        if name == "look_at_screen":
            return tr("Take a picture of what is on your screen", lang)
        if name == "print_file":
            file = Path(str(a.get("path", ""))).name
            if a.get("copies") and int(a["copies"]) > 1:
                return tr(
                    "Print {name} on paper ({copies} copies)", lang, name=file, copies=a["copies"]
                )
            return tr("Print {name} on paper", lang, name=file)
        if name == "serial_send":
            return tr(
                "Write to the board on {port}: {text}", lang, port=a.get("port"), text=a.get("text")
            )
        if name == "mqtt_publish":
            return tr(
                "Send to {topic} (MQTT): {message}",
                lang,
                topic=a.get("topic"),
                message=a.get("message"),
            )
        if name == "home_do":
            if a.get("entity"):
                return tr(
                    "Ask Home Assistant to do {service} on {entity}",
                    lang,
                    service=a.get("service"),
                    entity=a["entity"],
                )
            return tr("Ask Home Assistant to do {service}", lang, service=a.get("service"))
        if name == "modbus_write":
            return tr(
                "Write {values} at address {address} of {device} (Modbus)", lang,
                values=a.get("values"), address=a.get("address"), device=a.get("device"),
            )  # fmt: skip
    except Exception:  # noqa: BLE001 - odd arguments: the raw form is shown instead
        return None
    return None
