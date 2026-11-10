"""Things on the network: MQTT, Home Assistant, Modbus, and a look at what is around.

Three open ways cover most home and industrial devices:

* **MQTT** — small messages on named topics, through a "broker" (Mosquitto, the one inside
  Home Assistant…). Spoken by Zigbee2MQTT, Tasmota, ESPHome, Shelly, many sensors and robots.
* **Home Assistant** — a free home-automation hub that already knows thousands of devices;
  Datas asks it over its web interface with a token the person creates there.
* **Modbus TCP** — the common language of industrial equipment: PLCs, inverters, meters.

The addresses, the password and the token are in ``<home>/things.json`` (see datas.things).
"""

from __future__ import annotations

import socket
import struct
import threading
import time

import httpx

from datas.things import ThingError, settings
from datas.words import Said

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------


def _mqtt_client(cfg: dict | None = None):  # noqa: ANN202
    cfg = cfg or settings()["mqtt"]
    if not cfg.get("host"):
        raise ThingError(
            "No MQTT broker is set up. Add its address under Tools → Cameras, printers and "
            "other hardware → Home and industrial devices."
        )
    try:
        import paho.mqtt.client as mqtt
    except ImportError as e:
        raise ThingError("The MQTT part (paho-mqtt) is missing from this copy of Datas.") from e
    c = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=f"datas-{int(time.time()) % 100000}"
    )
    if cfg.get("username"):
        c.username_pw_set(cfg["username"], cfg.get("password") or None)
    if cfg.get("tls"):
        c.tls_set()
    try:
        c.connect(cfg["host"], int(cfg.get("port") or 1883), keepalive=30)
    except (OSError, ValueError) as e:
        raise ThingError(
            "Could not reach the MQTT broker at {host}: {why}", host=cfg["host"], why=str(e)
        ) from e
    return c


def _wait_connected(c, seconds: float = 8.0) -> None:  # noqa: ANN001
    end = time.time() + seconds
    while time.time() < end:
        if c.is_connected():
            return
        time.sleep(0.05)
    raise ThingError("The MQTT broker did not accept the connection (wrong user or password?).")


def mqtt_publish(topic: str, message: str, retain: bool = False, cfg: dict | None = None) -> str:
    if not topic or any(ch in topic for ch in "#+"):
        raise ThingError("To send, name one exact topic (no # or +).")
    c = _mqtt_client(cfg)
    c.loop_start()
    try:
        _wait_connected(c)
        info = c.publish(topic, message, qos=1, retain=bool(retain))
        info.wait_for_publish(8)
        if not info.is_published():
            raise ThingError("The broker did not confirm the message.")
    finally:
        c.loop_stop()
        c.disconnect()
    return Said("Sent to {topic}.", topic=topic)


def mqtt_read(
    topic: str, seconds: float = 5.0, limit: int = 50, cfg: dict | None = None
) -> list[dict]:
    """Messages arriving on ``topic`` (``#`` and ``+`` allowed) during ``seconds``; the kept
    ("retained") ones arrive at once."""
    seconds = max(0.5, min(float(seconds), 60.0))
    got: list[dict] = []
    c = _mqtt_client(cfg)

    def on_message(_c, _u, msg) -> None:  # noqa: ANN001
        if len(got) < limit:
            got.append(
                {"topic": msg.topic, "message": msg.payload.decode("utf-8", "replace")[:2000]}
            )

    def on_connect(client, _u, _f, _rc, _p=None) -> None:  # noqa: ANN001
        client.subscribe(topic or "#")

    c.on_message, c.on_connect = on_message, on_connect
    c.loop_start()
    try:
        _wait_connected(c)
        end = time.time() + seconds
        while time.time() < end and len(got) < limit:
            time.sleep(0.05)
    finally:
        c.loop_stop()
        c.disconnect()
    return got


# ---------------------------------------------------------------------------
# Home Assistant
# ---------------------------------------------------------------------------


def _ha(cfg: dict | None = None) -> httpx.Client:
    cfg = cfg or settings()["home_assistant"]
    if not cfg.get("url") or not cfg.get("token"):
        raise ThingError(
            "Home Assistant is not set up. Add its address and a long-lived access token "
            "(Home Assistant → your profile → Security) under Tools → Cameras, printers and "
            "other hardware → Home and industrial devices."
        )
    return httpx.Client(
        base_url=cfg["url"].rstrip("/"),
        headers={"Authorization": f"Bearer {cfg['token']}"},
        timeout=15,
        trust_env=False,
        transport=cfg.get("_transport"),  # tests
    )


def _ha_error(e: Exception) -> ThingError:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return ThingError(
                "Home Assistant refused the access token. Make a new one and save it again."
            )
        return ThingError(
            "Home Assistant answered with an error ({code}): {text}",
            code=code,
            text=e.response.text[:200],
        )
    return ThingError("Could not reach Home Assistant: {why}", why=str(e))


def home_states(domain: str | None = None, cfg: dict | None = None) -> list[dict]:
    """What Home Assistant knows: each thing, its state and its name. ``domain`` narrows it
    ("light", "switch", "sensor", "climate", "cover", "lock"…)."""
    try:
        with _ha(cfg) as c:
            r = c.get("/api/states")
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise _ha_error(e) from e
    out = []
    for s in data if isinstance(data, list) else []:
        eid = str(s.get("entity_id", ""))
        if domain and not eid.startswith(domain.strip(".") + "."):
            continue
        attrs = s.get("attributes") or {}
        out.append(
            {
                "id": eid,
                "state": str(s.get("state", ""))
                + (f" {attrs['unit_of_measurement']}" if attrs.get("unit_of_measurement") else ""),
                "name": str(attrs.get("friendly_name") or ""),
            }
        )
    return out


def home_call(
    service: str, entity: str | None = None, data: dict | None = None, cfg: dict | None = None
) -> str:
    """Ask Home Assistant to do something: ``service`` is "light.turn_on", "switch.toggle",
    "climate.set_temperature", "cover.open_cover", "scene.turn_on"…"""
    if service.count(".") != 1 or not all(
        part.replace("_", "").isalnum() for part in service.split(".")
    ):
        raise ThingError('A service looks like "light.turn_on".')
    body = dict(data or {})
    if entity:
        body["entity_id"] = entity
    try:
        with _ha(cfg) as c:
            r = c.post("/api/services/" + service.replace(".", "/"), json=body)
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise _ha_error(e) from e
    if entity:
        return Said("Home Assistant did {service} on {entity}.", service=service, entity=entity)
    return Said("Home Assistant did {service}.", service=service)


# ---------------------------------------------------------------------------
# Modbus TCP
# ---------------------------------------------------------------------------

MODBUS_ERRORS = {
    1: "the device does not know that kind of request",
    2: "there is nothing at that address in the device",
    3: "the device does not accept that value",
    4: "the device failed while doing it",
    6: "the device is busy",
}
READ_CODES = {"coil": 1, "discrete": 2, "holding": 3, "input": 4}


def modbus_device(name: str) -> dict:
    devices = settings()["modbus"]
    for d in devices:
        if d["name"].lower() == str(name).strip().lower():
            return d
    if devices:
        raise ThingError(
            "There is no Modbus device called {name}. Set up: {names}",
            name=repr(name),
            names=", ".join(d["name"] for d in devices),
        )
    raise ThingError(
        "There is no Modbus device called {name}. None is set up yet (Tools → Cameras, "
        "printers and other hardware).",
        name=repr(name),
    )


def _modbus(dev: dict, pdu: bytes) -> bytes:
    tid = int(time.time() * 1000) & 0xFFFF
    frame = struct.pack(">HHHB", tid, 0, len(pdu) + 1, int(dev.get("unit", 1)) & 0xFF) + pdu
    try:
        with socket.create_connection((dev["host"], int(dev.get("port", 502))), timeout=6) as s:
            s.settimeout(6)
            s.sendall(frame)
            head = _exactly(s, 7)
            rtid, proto, length, _unit = struct.unpack(">HHHB", head)
            if rtid != tid or proto != 0 or not 2 <= length <= 256:
                raise ThingError("The device answered with something that is not Modbus.")
            body = _exactly(s, length - 1)
    except OSError as e:
        raise ThingError(
            "Could not reach the device at {host}:{port}: {why}",
            host=dev["host"],
            port=dev.get("port", 502),
            why=str(e),
        ) from e
    if body[0] == (pdu[0] | 0x80):
        raise ThingError(
            "The device refused: {why}.", why=MODBUS_ERRORS.get(body[1]) or f"error {body[1]}"
        )
    if body[0] != pdu[0]:
        raise ThingError("The device answered a different question than the one asked.")
    return body[1:]


def _exactly(s: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise OSError("the device closed the connection")
        buf += chunk
    return buf


def modbus_read(dev: dict, kind: str, address: int, count: int = 1) -> list[int]:
    """``kind``: holding | input (numbers, 0–65535) or coil | discrete (on/off as 1/0)."""
    if kind not in READ_CODES:
        raise ThingError("kind is one of: holding, input, coil, discrete.")
    address, count = int(address), int(count)
    top = 125 if kind in ("holding", "input") else 2000
    if not (0 <= address <= 0xFFFF and 1 <= count <= top):
        raise ThingError("Ask for 1 to {top} values, at an address from 0 to 65535.", top=top)
    data = _modbus(dev, struct.pack(">BHH", READ_CODES[kind], address, count))
    payload = data[1 : 1 + data[0]]
    if kind in ("holding", "input"):
        if len(payload) != 2 * count:
            raise ThingError("The device sent fewer values than asked.")
        return list(struct.unpack(f">{count}H", payload))
    bits = (
        [(payload[i // 8] >> (i % 8)) & 1 for i in range(count)]
        if len(payload) * 8 >= count
        else None
    )
    if bits is None:
        raise ThingError("The device sent fewer values than asked.")
    return bits


def modbus_write(dev: dict, kind: str, address: int, values: list[int]) -> str:
    """``kind``: holding (numbers) or coil (on/off)."""
    address = int(address)
    vals = [int(v) for v in values]
    if kind not in ("holding", "coil") or not vals or not 0 <= address <= 0xFFFF:
        raise ThingError(
            "Only holding registers and coils can be written; give at least one value."
        )
    if kind == "holding":
        if any(not 0 <= v <= 0xFFFF for v in vals) or len(vals) > 123:
            raise ThingError("A holding register takes a whole number from 0 to 65535.")
        if len(vals) == 1:
            _modbus(dev, struct.pack(">BHH", 6, address, vals[0]))
        else:
            _modbus(
                dev,
                struct.pack(">BHHB", 16, address, len(vals), 2 * len(vals))
                + struct.pack(f">{len(vals)}H", *vals),
            )
    else:
        if len(vals) == 1:
            _modbus(dev, struct.pack(">BHH", 5, address, 0xFF00 if vals[0] else 0))
        else:
            packed = bytearray((len(vals) + 7) // 8)
            for i, v in enumerate(vals):
                if v:
                    packed[i // 8] |= 1 << (i % 8)
            _modbus(dev, struct.pack(">BHHB", 15, address, len(vals), len(packed)) + bytes(packed))
    return Said(
        "Wrote {n} value(s) at {address} on {name}.",
        n=len(vals),
        address=address,
        name=dev.get("name") or dev["host"],
    )


# ---------------------------------------------------------------------------
# does a connection that was set up work?
# ---------------------------------------------------------------------------


def check(what: str, name: str | None = None) -> Said:
    """Try one of the connections and say in a sentence how it went (ThingError if not)."""
    if what == "mqtt":
        c = _mqtt_client()
        c.loop_start()
        try:
            _wait_connected(c)
        finally:
            c.loop_stop()
            c.disconnect()
        return Said("The MQTT broker accepted the connection.")
    if what == "home_assistant":
        n = len(home_states())
        return Said("Home Assistant answered: it knows {n} things.", n=n)
    if what == "modbus":
        dev = modbus_device(name or "")
        try:
            vals = modbus_read(dev, "holding", 0, 1)
        except ThingError as e:
            if e.text.startswith("The device refused"):
                # it speaks Modbus; it just has nothing at address 0, which is common
                return Said(
                    "{name} answers (it has nothing at address 0, which is normal).",
                    name=dev["name"],
                )
            raise
        return Said(
            "{name} answers; the value at address 0 is {value}.", name=dev["name"], value=vals[0]
        )
    raise ThingError("Check one of: mqtt, home_assistant, modbus.")


# ---------------------------------------------------------------------------
# what is on this network (devices that announce themselves; nothing is probed)
# ---------------------------------------------------------------------------

# How a device says what it is (mDNS / Bonjour service types), in plain words.
KINDS = {
    "_ipp._tcp": "printer",
    "_ipps._tcp": "printer",
    "_printer._tcp": "printer",
    "_pdl-datastream._tcp": "printer",
    "_scanner._tcp": "scanner",
    "_uscan._tcp": "scanner",
    "_smb._tcp": "shared folders (a NAS or a computer)",
    "_afpovertcp._tcp": "shared folders (a NAS or a Mac)",
    "_nfs._tcp": "shared folders (NFS)",
    "_ssh._tcp": "computer that accepts remote log-in (SSH), such as a Raspberry Pi",
    "_sftp-ssh._tcp": "computer that accepts file transfer (SFTP)",
    "_workstation._tcp": "computer",
    "_home-assistant._tcp": "Home Assistant",
    "_hap._tcp": "smart-home device (HomeKit)",
    "_matter._tcp": "smart-home device (Matter)",
    "_esphomelib._tcp": "ESPHome board",
    "_mqtt._tcp": "MQTT broker",
    "_googlecast._tcp": "Chromecast or a screen with Google Cast",
    "_airplay._tcp": "screen or speaker with AirPlay",
    "_raop._tcp": "speaker with AirPlay",
    "_spotify-connect._tcp": "speaker",
    "_rtsp._tcp": "camera or video stream",
    "_octoprint._tcp": "3D printer (OctoPrint)",
    "_datas-link._tcp": "computer with Datas",
    "_http._tcp": "device with a web page",
    "_https._tcp": "device with a web page",
}


def kind_of(service_type: str) -> str:
    return KINDS.get(service_type.replace(".local.", "").rstrip("."), "")


def _ssdp(seconds: float) -> list[dict]:
    """Devices that answer the UPnP call (routers, TVs, media servers, some NAS)."""
    msg = (
        b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
        b"MX: 1\r\nST: upnp:rootdevice\r\n\r\n"
    )
    found: dict[str, dict] = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.sendto(msg, ("239.255.255.250", 1900))
        end = time.time() + seconds
        while time.time() < end:
            try:
                data, (ip, _port) = s.recvfrom(4096)
            except TimeoutError:
                continue
            head = {}
            for line in data.decode("utf-8", "replace").split("\r\n")[1:]:
                k, _, v = line.partition(":")
                head[k.strip().lower()] = v.strip()
            found.setdefault(
                ip,
                {
                    "address": ip,
                    "name": head.get("server", "")[:80],
                    "kind": "device that announces itself (UPnP)",
                    "page": head.get("location", ""),
                },
            )
        s.close()
    except OSError:
        pass
    return list(found.values())


def around(seconds: float = 3.0) -> list[dict]:
    """Devices on this network that announce themselves (mDNS/Bonjour and UPnP). Nothing is
    scanned or probed: this only listens to what devices say about themselves."""
    seconds = max(1.0, min(float(seconds), 10.0))
    out: dict[tuple, dict] = {}
    ssdp: list[dict] = []
    t = threading.Thread(target=lambda: ssdp.extend(_ssdp(seconds)), daemon=True)
    t.start()
    try:
        from zeroconf import ServiceBrowser, Zeroconf, ZeroconfServiceTypes

        types = [x for x in ZeroconfServiceTypes.find(timeout=min(2.0, seconds / 2)) if kind_of(x)]
        zc = Zeroconf()
        try:

            class Seen:
                def add_service(self, zc_, type_, name) -> None:  # noqa: ANN001
                    info = zc_.get_service_info(type_, name, timeout=1200)
                    if not info:
                        return
                    for addr in info.parsed_addresses():
                        if ":" in addr:
                            continue
                        key = (addr, kind_of(type_))
                        out.setdefault(
                            key,
                            {
                                "address": addr,
                                "name": name.replace("." + type_, ""),
                                "kind": kind_of(type_),
                                "port": info.port,
                                "host": (info.server or "").rstrip("."),
                            },
                        )

                def update_service(self, *a) -> None:  # noqa: ANN002
                    pass

                def remove_service(self, *a) -> None:  # noqa: ANN002
                    pass

            browsers = [ServiceBrowser(zc, x, Seen()) for x in types]
            time.sleep(max(0.5, seconds / 2))
            for b in browsers:
                b.cancel()
        finally:
            zc.close()
    except Exception:  # noqa: BLE001 - no network, mDNS blocked: UPnP may still answer
        pass
    t.join(seconds + 1)
    known = {d["address"] for d in out.values()}
    rest = [d for d in ssdp if d["address"] not in known]
    return sorted(out.values(), key=lambda d: (d["kind"], d["name"])) + rest
