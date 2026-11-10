"""Hardware and devices on the network: camera, screen, printers, serial boards, MQTT,
Home Assistant, Modbus, mouse and keyboard — against stand-ins that speak the real protocols."""

from __future__ import annotations

import io
import json
import shutil
import sys

import httpx
import pytest

from datas import things
from datas.things import ThingError, control, local, net

from .fake_things import Board, Broker, ModbusDevice, ModbusOnACable

PATTERN = ["-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=10"]  # FFmpeg's own test picture


def jpeg(width: int, height: int) -> bytes:
    """A real (plain grey) JPEG of that size."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 120, 120)).save(buf, "JPEG")
    return buf.getvalue()


# ---- settings -------------------------------------------------------------------------


def test_settings_keep_secrets_out_of_what_the_window_sees(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    assert things.public_settings()["mqtt"] == {
        "host": "",
        "port": 1883,
        "username": "",
        "tls": False,
        "password_set": False,
    }
    shown = things.save_settings(
        {
            "mqtt": {
                "host": "192.168.1.10",
                "port": "1884",
                "username": "home",
                "password": "s3cret",
            },
            "home_assistant": {"url": "http://ha.local:8123", "token": "TOKEN"},
            "modbus": [
                {"name": " Inverter ", "host": "192.168.1.50"},
                {"name": "broken"},
                "nonsense",
            ],
        }
    )
    assert (
        shown["mqtt"]["password_set"]
        and "password" not in shown["mqtt"]
        and shown["mqtt"]["port"] == 1884
    )
    assert shown["home_assistant"] == {"url": "http://ha.local:8123", "token_set": True}
    assert shown["modbus"] == [{"name": "Inverter", "host": "192.168.1.50", "port": 502, "unit": 1}]
    # an empty password keeps the old one; "-" removes it
    things.save_settings({"mqtt": {"password": ""}})
    assert things.settings()["mqtt"]["password"] == "s3cret"
    things.save_settings({"mqtt": {"password": "-"}})
    assert things.settings()["mqtt"]["password"] == ""
    if sys.platform != "win32":
        assert things.settings_path().stat().st_mode & 0o077 == 0
    # emptying the address forgets the connection's secret too
    things.save_settings({"mqtt": {"password": "again"}, "home_assistant": {"url": ""}})
    assert (
        things.settings()["mqtt"]["password"] == "again"
        and things.settings()["home_assistant"]["token"] == ""
    )
    things.save_settings({"mqtt": {"host": ""}})
    assert (
        things.settings()["mqtt"]["password"] == "" and things.settings()["mqtt"]["username"] == ""
    )
    # a damaged file is not fatal
    things.settings_path().write_text("{not json")
    assert things.settings()["mqtt"]["host"] == ""


# ---- camera, screen, printers ------------------------------------------------------------


def test_camera_lists_are_read_from_each_system():
    win_new = """[dshow @ 0000] "Integrated Camera" (video)
[dshow @ 0000]   Alternative name "@device_pnp_\\\\?\\usb#vid_04f2"
[dshow @ 0000] "Microphone (Realtek Audio)" (audio)
[dshow @ 0000] "USB2.0 HD UVC WebCam" (video)"""
    assert local.parse_dshow(win_new) == [
        {"id": "Integrated Camera", "name": "Integrated Camera"},
        {"id": "USB2.0 HD UVC WebCam", "name": "USB2.0 HD UVC WebCam"},
    ]
    win_old = '''[dshow @ 01] DirectShow video devices (some may be both video and audio devices)
[dshow @ 01]  "HD Webcam"
[dshow @ 01]     Alternative name "@device_pnp_x"
[dshow @ 01] DirectShow audio devices
[dshow @ 01]  "Microphone"'''
    assert local.parse_dshow(win_old) == [{"id": "HD Webcam", "name": "HD Webcam"}]
    mac = """[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1] [1] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone"""
    assert local.parse_avfoundation(mac) == [{"id": "0", "name": "FaceTime HD Camera"}]
    assert local.parse_lpstat("Office_Laser\nPDF\n", "system default destination: PDF\n") == [
        {"name": "Office_Laser", "default": False},
        {"name": "PDF", "default": True},
    ]
    assert local.parse_lpstat("", "no system default destination") == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs FFmpeg")
def test_a_photo_comes_out_of_the_real_capture_path():
    # a test pattern stands in for the camera; everything else is the real thing
    jpg = local.photo(source=PATTERN, width=640)
    from PIL import Image

    im = Image.open(io.BytesIO(jpg))
    assert im.format == "JPEG" and im.size == (640, 360)
    with pytest.raises(ThingError) as e:
        local.photo(source=["-f", "lavfi", "-i", "this-is-not-a-source"])
    assert "Could not take a picture" in str(e.value)


def test_the_screen_is_made_smaller_for_the_ai(monkeypatch):
    from PIL import Image, ImageGrab

    monkeypatch.setattr(ImageGrab, "grab", lambda **k: Image.new("RGBA", (3840, 2160), "white"))
    jpg = local.screenshot(width=1600)
    im = Image.open(io.BytesIO(jpg))
    assert im.format == "JPEG" and im.size == (1600, 900)
    assert local.screens() == [{"id": "all", "width": 3840, "height": 2160}]

    def no_display(**k):
        raise OSError("X connection failed")

    monkeypatch.setattr(ImageGrab, "grab", no_display)
    assert local.screens() == []
    with pytest.raises(ThingError) as e:
        local.screenshot()
    assert "could not look at the screen" in str(e.value)


@pytest.mark.skipif(sys.platform == "win32", reason="the lp path is for Linux and macOS")
def test_printing_goes_to_the_right_printer_and_says_so(tmp_path, monkeypatch):
    calls = []

    class Done:
        def __init__(self, out="", code=0):
            self.stdout, self.stderr, self.returncode = out, "", code

    def fake_run(cmd, timeout=20):
        calls.append(cmd)
        if cmd[:2] == ["lpstat", "-e"]:
            return Done("Office_Laser\nKitchen\n")
        if cmd[:2] == ["lpstat", "-d"]:
            return Done("system default destination: Kitchen\n")
        return Done("request id is Kitchen-12 (1 file(s))\n")

    monkeypatch.setattr(local, "_run", fake_run)
    monkeypatch.setattr(local.shutil, "which", lambda name: "/usr/bin/" + name)
    from datas import programs

    monkeypatch.setattr(programs, "find", lambda pid: None)
    doc = tmp_path / "letter.pdf"
    doc.write_bytes(b"%PDF-1.4")
    assert local.print_file(doc) == "Sent letter.pdf to the printer Kitchen."
    assert calls[-1] == ["lp", "-d", "Kitchen", "-n", "1", str(doc)]
    assert "3 copies" in local.print_file(doc, "Office_Laser", 3)
    assert calls[-1][:5] == ["lp", "-d", "Office_Laser", "-n", "3"]
    with pytest.raises(ThingError) as e:
        local.print_file(doc, "Nowhere")
    assert "Office_Laser, Kitchen" in str(e.value)
    with pytest.raises(ThingError):
        local.print_file(tmp_path / "missing.pdf")
    word = tmp_path / "letter.docx"
    word.write_bytes(b"x")
    with pytest.raises(ThingError) as e:  # no LibreOffice to make the PDF
        local.print_file(word)
    assert "LibreOffice" in str(e.value)


def test_windows_prints_text_and_pictures_with_nothing_but_windows(tmp_path, monkeypatch):
    """Windows cannot print a file by itself; Datas does it with a small PowerShell program.
    Here the program is not run (see the next test for that): this checks what is handed to it."""
    import base64

    from datas import programs

    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        local,
        "printers",
        lambda: [{"name": "Office", "default": True}, {"name": "Lab's printer", "default": False}],
    )
    monkeypatch.setattr(programs, "find", lambda pid: None)  # no LibreOffice
    assert local.answer_format() == "txt"  # an answer is printed as text there
    ran = []

    def fake_run(cmd, timeout=20, env=None):
        ran.append((cmd, env))
        return local.subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(local, "_run", fake_run)
    note = tmp_path / "it's a note.txt"
    note.write_text("hola", encoding="utf-8")
    said = local.print_file(note, "Lab's printer", copies=2)
    assert said == "Sent it's a note.txt to the printer Lab's printer, 2 copies."
    cmd, env = ran[0]
    assert cmd[0] == "powershell" and cmd[-2] == "-EncodedCommand"
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert (
        script == local.WINDOWS_PRINT and "note" not in script and "Lab" not in script
    )  # nothing pasted in
    assert env["DATAS_PRINT_FILE"] == str(note) and env["DATAS_PRINTER"] == "Lab's printer"
    assert (
        env["DATAS_COPIES"] == "2"
        and env["DATAS_PRINT_KIND"] == "text"
        and env["DATAS_PRINT_TO"] == ""
    )
    pic = tmp_path / "foto.png"
    pic.write_bytes(b"x")
    local.print_file(pic)
    assert ran[1][1]["DATAS_PRINT_KIND"] == "picture" and ran[1][1]["DATAS_PRINTER"] == "Office"
    # the program's own complaint comes back as a sentence
    monkeypatch.setattr(
        local,
        "_run",
        lambda cmd, timeout=20, env=None: local.subprocess.CompletedProcess(
            cmd, 3, "", "that printer cannot be used\n"
        ),
    )
    with pytest.raises(ThingError) as e:
        local.print_file(note)
    assert e.value.say("es") == "La impresora no lo aceptó: esa impresora no se puede usar"
    # with LibreOffice a PDF can be printed, so answers keep their layout
    monkeypatch.setattr(
        programs, "find", lambda pid: "C:/LibreOffice/soffice.exe" if pid == "libreoffice" else None
    )
    assert local.answer_format() == "pdf"
    monkeypatch.setattr(local.platform, "system", lambda: "Linux")
    assert local.answer_format() == "pdf"


@pytest.mark.skipif(sys.platform != "win32", reason="the real Windows printing program")
def test_windows_really_prints_to_a_file(tmp_path):
    """The real thing on a real Windows: text and a picture go through the printing system
    into a file, using the printer "Microsoft Print to PDF" that Windows brings along."""
    target = next(
        (p["name"] for p in local.printers() if p["name"] == "Microsoft Print to PDF"), None
    )
    if not target:
        pytest.skip(f"this Windows has no 'Microsoft Print to PDF' printer: {local.printers()}")
    note = tmp_path / "nota.txt"
    note.write_text(
        "Lista de compras\n\n- pan\n- leche\n" + "Una línea larga con eñes y acentos. " * 400,
        encoding="utf-8",
    )
    out = tmp_path / "nota.pdf"
    said = local.print_file(note, target, to_file=out)
    assert "nota.txt" in said and out.is_file() and out.stat().st_size > 2000, (
        out.stat().st_size if out.exists() else "no file"
    )
    assert out.read_bytes()[:4] == b"%PDF"
    pic = tmp_path / "foto.png"
    pic.write_bytes(_png(300, 200))
    out2 = tmp_path / "foto.pdf"
    local.print_file(pic, target, to_file=out2)
    assert out2.is_file() and out2.read_bytes()[:4] == b"%PDF"
    with pytest.raises(ThingError):
        local._windows_print(note, "text", "There is no such printer", 1, tmp_path / "x.pdf")


def _png(width: int, height: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (40, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


# ---- a board on a serial port ---------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX")
def test_talking_to_a_board_on_a_serial_port():
    pytest.importorskip("serial")
    board = Board()
    try:
        said = local.serial_talk(board.port, "LED ON", seconds=0.6, baud=115200, settle=0.3)
        assert "READY v1" in said and "OK led=1" in said
        assert "TEMP 21.5" in local.serial_talk(board.port, "TEMP?", seconds=0.6, settle=0.1)
        assert board.got[:2] == ["LED ON", "TEMP?"]
        assert "READY" not in local.serial_talk(board.port, None, seconds=0.3)  # only listening
    finally:
        board.close()
    with pytest.raises(ThingError) as e:
        local.serial_talk("/dev/ttyDOESNOTEXIST", "x")
    assert "Is the board plugged in" in str(e.value)


def test_serial_ports_are_named_in_plain_words(monkeypatch):
    pytest.importorskip("serial")
    from serial.tools import list_ports

    class P:
        def __init__(self, device, vid, pid, description="n/a", manufacturer=None):
            self.device, self.vid, self.pid = device, vid, pid
            self.description, self.manufacturer = description, manufacturer

    monkeypatch.setattr(
        list_ports,
        "comports",
        lambda: [
            P("/dev/ttyUSB0", 0x1A86, 0x7523, "USB Serial"),
            P("/dev/ttyACM0", 0x2341, 0x0043, "Arduino Uno", "Arduino (www.arduino.cc)"),
            P("/dev/ttyS0", None, None),  # a motherboard port with nothing on it
            P("/dev/ttyACM1", 0x9999, 0x0001, "Lab scale"),
        ],
    )
    ports = local.serial_ports()
    assert [p["port"] for p in ports] == ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"]
    assert ports[0]["what"] == "Arduino board" and ports[0]["usb"] == "2341:0043"
    assert ports[1]["what"] == "Lab scale" and "CH340" in ports[2]["what"]


# ---- MQTT -----------------------------------------------------------------------------------


def test_mqtt_send_and_read_through_a_real_broker_conversation():
    pytest.importorskip("paho.mqtt.client")
    broker = Broker(password="pw")
    cfg = {
        "host": "127.0.0.1",
        "port": broker.port,
        "username": "home",
        "password": "pw",
        "tls": False,
    }
    try:
        assert (
            net.mqtt_publish("home/kitchen/light/set", "ON", cfg=cfg)
            == "Sent to home/kitchen/light/set."
        )
        assert broker.seen == [("home/kitchen/light/set", b"ON")]
        net.mqtt_publish("home/kitchen/temp", "21.5", retain=True, cfg=cfg)
        # the kept message is there for whoever asks later, wildcards included
        got = net.mqtt_read("home/+/temp", seconds=1.0, cfg=cfg)
        assert got == [{"topic": "home/kitchen/temp", "message": "21.5"}]
        with pytest.raises(ThingError):
            net.mqtt_publish("home/#", "x", cfg=cfg)  # sending needs one exact topic
        with pytest.raises(ThingError) as e:
            net.mqtt_publish("a/b", "x", cfg={**cfg, "password": "wrong"})
        assert "did not accept" in str(e.value)
    finally:
        broker.close()
    with pytest.raises(ThingError) as e:
        net.mqtt_publish("a/b", "x", cfg={"host": ""})
    assert "No MQTT broker is set up" in str(e.value)
    assert (
        Broker.matches("a/#", "a/b/c")
        and Broker.matches("a/+/c", "a/b/c")
        and not Broker.matches("a/+", "a/b/c")
    )


# ---- Home Assistant ---------------------------------------------------------------------------


def test_home_assistant_states_and_calls():
    asked = []

    def hub(request: httpx.Request) -> httpx.Response:
        asked.append(
            (
                request.method,
                request.url.path,
                request.headers.get("authorization"),
                request.content,
            )
        )
        if request.headers.get("authorization") != "Bearer GOOD":
            return httpx.Response(401, text="401: Unauthorized")
        if request.url.path == "/api/states":
            return httpx.Response(
                200,
                json=[
                    {
                        "entity_id": "light.kitchen",
                        "state": "off",
                        "attributes": {"friendly_name": "Kitchen light"},
                    },
                    {
                        "entity_id": "sensor.patio",
                        "state": "18.4",
                        "attributes": {"unit_of_measurement": "°C", "friendly_name": "Patio"},
                    },
                ],
            )
        return httpx.Response(200, json=[])

    cfg = {"url": "http://ha.local:8123/", "token": "GOOD", "_transport": httpx.MockTransport(hub)}
    assert net.home_states(cfg=cfg) == [
        {"id": "light.kitchen", "state": "off", "name": "Kitchen light"},
        {"id": "sensor.patio", "state": "18.4 °C", "name": "Patio"},
    ]
    assert [s["id"] for s in net.home_states("light", cfg=cfg)] == ["light.kitchen"]
    assert (
        net.home_call("light.turn_on", "light.kitchen", {"brightness": 120}, cfg=cfg)
        == "Home Assistant did light.turn_on on light.kitchen."
    )
    method, path, _auth, body = asked[-1]
    assert (method, path) == ("POST", "/api/services/light/turn_on")
    assert json.loads(body) == {"brightness": 120, "entity_id": "light.kitchen"}
    with pytest.raises(ThingError) as e:
        net.home_states(cfg={**cfg, "token": "BAD"})
    assert "refused the access token" in str(e.value)
    with pytest.raises(ThingError):
        net.home_call("../../etc", cfg=cfg)
    with pytest.raises(ThingError) as e:
        net.home_states(cfg={"url": "", "token": ""})
    assert "not set up" in str(e.value)


# ---- Modbus ------------------------------------------------------------------------------------


def test_modbus_reads_and_writes_against_a_device():
    device = ModbusDevice()
    dev = {"name": "inverter", "host": "127.0.0.1", "port": device.port, "unit": 7}
    try:
        device.registers.update({10: 230, 11: 50, 12: 65535})
        assert net.modbus_read(dev, "holding", 10, 3) == [230, 50, 65535]
        assert net.modbus_read(dev, "input", 11, 1) == [50]
        assert net.modbus_write(dev, "holding", 20, [1234]) == "Wrote 1 value(s) at 20 on inverter."
        net.modbus_write(dev, "holding", 21, [1, 2, 3])
        assert [device.registers[a] for a in (20, 21, 22, 23)] == [1234, 1, 2, 3]
        net.modbus_write(dev, "coil", 3, [1])
        net.modbus_write(dev, "coil", 8, [1, 0, 1, 1, 0, 0, 0, 0, 1])
        assert net.modbus_read(dev, "coil", 0, 17) == [
            0,
            0,
            0,
            1,
            0,
            0,
            0,
            0,
            1,
            0,
            1,
            1,
            0,
            0,
            0,
            0,
            1,
        ]
        assert net.modbus_read(dev, "discrete", 3, 1) == [1]
        with pytest.raises(ThingError) as e:
            net.modbus_read(dev, "holding", 500, 1)
        assert "nothing at that address" in str(e.value)
        for bad in (("holding", 0, [70000]), ("input", 0, [1]), ("coil", 0, [])):
            with pytest.raises(ThingError):
                net.modbus_write(dev, *bad)
        with pytest.raises(ThingError):
            net.modbus_read(dev, "holding", 0, 500)
    finally:
        device.close()
    with pytest.raises(ThingError) as e:
        net.modbus_read({**dev, "port": 1}, "holding", 0, 1)
    assert "Could not reach the device" in str(e.value)


@pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX")
def test_modbus_on_a_serial_cable(tmp_path, monkeypatch):
    """Modbus RTU: the same questions as on the network, framed for a cable (unit number
    first, checksum last) — against a device on a pseudo-terminal."""
    pytest.importorskip("serial")
    # the checksum of the textbook message "read 10 registers from unit 1": C5 CD on the wire
    assert net.crc16(bytes.fromhex("01030000000A")) == 0xCDC5
    meter = ModbusOnACable(unit=5)
    dev = {"name": "meter", "serial": meter.port, "baud": 19200, "unit": 5, "timeout": 0.6}
    try:
        meter.registers.update({0: 2301, 1: 50, 2: 65535})
        assert net.modbus_read(dev, "holding", 0, 3) == [2301, 50, 65535]
        assert net.modbus_read(dev, "input", 1, 1) == [50]
        assert net.modbus_write(dev, "holding", 7, [42]) == "Wrote 1 value(s) at 7 on meter."
        net.modbus_write(dev, "holding", 8, [1, 2, 3])
        net.modbus_write(dev, "coil", 2, [1])
        net.modbus_write(dev, "coil", 9, [1, 0, 1])
        assert [meter.registers[a] for a in (7, 8, 9, 10)] == [42, 1, 2, 3]
        assert net.modbus_read(dev, "coil", 0, 12) == [0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 1]
        with pytest.raises(ThingError) as e:
            net.modbus_read(dev, "holding", 500, 1)
        assert "nothing at that address" in str(e.value)
        # another unit number: nobody on the cable answers, and the sentence says what to check
        with pytest.raises(ThingError) as e:
            net.modbus_read({**dev, "unit": 9}, "holding", 0, 1)
        assert "did not answer" in str(e.value) and "(9)" in str(e.value)
        assert "no respondió" in e.value.say("es")
        meter.damage = True  # a wrong speed or a loose wire garbles the answer
        with pytest.raises(ThingError) as e:
            net.modbus_read(dev, "holding", 0, 1)
        assert "arrived damaged" in str(e.value)
        meter.damage = False

        # saved from the window like any other device, and checked by name
        monkeypatch.setenv("DATAS_HOME", str(tmp_path))
        things.save_settings(
            {
                "modbus": [
                    {"name": "Meter", "serial": meter.port, "baud": 19200, "unit": 5},
                    {"name": "Pump", "serial": "COM7", "parity": "e", "unit": 2},
                    {"name": "Inverter", "host": "10.0.0.9"},
                    {"name": "nothing given"},
                ]
            }
        )
        saved = things.settings()["modbus"]
        assert saved == [
            {"name": "Meter", "serial": meter.port, "baud": 19200, "parity": "N", "unit": 5},
            {"name": "Pump", "serial": "COM7", "baud": 9600, "parity": "E", "unit": 2},
            {"name": "Inverter", "host": "10.0.0.9", "port": 502, "unit": 1},
        ]
        assert net.check("modbus", "meter") == "Meter answers; the value at address 0 is 2301."
        # a setting the port does not accept is a sentence too (Linux: a pseudo-terminal
        # has no parity), never a crash
        try:
            net.modbus_read({**dev, "parity": "E"}, "holding", 0, 1)
        except ThingError as refused:
            assert "Could not use" in str(refused)
    finally:
        meter.close()
    with pytest.raises(ThingError) as e:
        net.modbus_read({**dev, "serial": "/dev/ttyNOPE"}, "holding", 0, 1)
    assert "Could not use /dev/ttyNOPE" in str(e.value)


def test_what_devices_say_they_are():
    assert net.kind_of("_ipp._tcp.local.") == "printer"
    assert "NAS" in net.kind_of("_smb._tcp.local.")
    assert "Raspberry Pi" in net.kind_of("_ssh._tcp.local.")
    assert net.kind_of("_esphomelib._tcp.local.") == "ESPHome board"
    assert net.kind_of("_something-else._tcp.local.") == ""


# ---- mouse and keyboard --------------------------------------------------------------------------


class FakeGui:
    def __init__(self):
        self.did = []

    def size(self):
        return (1920, 1080)

    def moveTo(self, x, y, duration=0):  # noqa: N802 - PyAutoGUI's name
        self.did.append(("move", x, y))

    def click(self, x, y, button="left"):
        self.did.append(("click", x, y, button))

    def doubleClick(self, x, y):  # noqa: N802
        self.did.append(("double", x, y))

    def write(self, text, interval=0):
        self.did.append(("write", text))

    def hotkey(self, *keys):
        self.did.append(("keys", keys))

    def scroll(self, n):
        self.did.append(("scroll", n))


def test_mouse_and_keyboard_actions_and_their_limits():
    g = FakeGui()
    assert control.act("click", 100, 200, gui=g) == "Done: Click at (100, 200)"
    control.act("right_click", 5, 5, gui=g)
    control.act("double_click", 6, 6, gui=g)
    control.act("move", 7, 7, gui=g)
    control.act("type", text="hola ñ", gui=g)
    control.act("key", keys="Ctrl+S", gui=g)
    control.act("scroll", amount=-3, gui=g)
    assert g.did == [
        ("click", 100, 200, "left"),
        ("click", 5, 5, "right"),
        ("double", 6, 6),
        ("move", 7, 7),
        ("write", "hola ñ"),
        ("keys", ("ctrl", "s")),
        ("scroll", -3),
    ]
    for bad in (
        {"action": "format_disk"},
        {"action": "click"},  # no place
        {"action": "click", "x": 5000, "y": 10},  # outside the screen
        {"action": "type"},
        {"action": "key", "keys": " "},
    ):
        with pytest.raises(ThingError):
            control.act(gui=g, **bad)
    assert (
        control.describe("type", text="x" * 500).startswith("Type: 'xxx")
        and len(control.describe("type", text="x" * 500)) < 220
    )
    assert control.describe("scroll", amount=4) == "Scroll up 4"

    class Corner(FakeGui):
        def click(self, x, y, button="left"):
            raise type("FailSafeException", (Exception,), {})()

    with pytest.raises(ThingError) as e:
        control.act("click", 1, 1, gui=Corner())
    assert "corner" in str(e.value)


def test_a_place_in_the_picture_of_the_screen_becomes_the_same_place_for_the_mouse():
    """The AI reads x and y from a picture that is smaller than the screen (and, on a Mac
    with a Retina screen, has twice as many dots as the mouse counts)."""
    g = FakeGui()  # the mouse counts 1920 x 1080
    control.act("click", 800, 450, gui=g, picture=(1600, 900))
    assert g.did == [("click", 960, 540, "left")]
    assert control.to_screen(1599, 899, (1600, 900), (1920, 1080)) == (1919, 1079)
    assert control.to_screen(1600, 1000, (3200, 2000), (1600, 1000)) == (800, 500)  # Retina
    with pytest.raises(ThingError) as e:  # outside the picture the AI was shown
        control.act("click", 1700, 10, gui=g, picture=(1600, 900))
    assert "1600 by 900" in str(e.value)


def test_the_inventory_never_fails_and_reads_as_text(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    monkeypatch.setattr(local, "cameras", lambda: [{"id": "/dev/video0", "name": "HD Webcam"}])
    monkeypatch.setattr(local, "screens", lambda: [{"id": "all", "width": 1920, "height": 1080}])
    monkeypatch.setattr(local, "serial_ports", lambda: [{"port": "COM3", "what": "Arduino board"}])

    def broken():
        raise ThingError("the printing service is not running")

    monkeypatch.setattr(local, "printers", broken)
    things.save_settings(
        {"mqtt": {"host": "10.0.0.2"}, "modbus": [{"name": "meter", "host": "10.0.0.9"}]}
    )
    inv = things.inventory()
    assert inv["cameras"][0]["name"] == "HD Webcam" and inv["printers"] == []
    assert inv["problems"] == {"printers": "the printing service is not running"}
    assert inv["connections"] == {"mqtt": True, "home_assistant": False, "modbus": ["meter"]}
    text = things.describe(inv)
    assert "/dev/video0 (HD Webcam)" in text and "COM3 — Arduino board" in text
    assert "MQTT, Modbus device 'meter'" in text and "printers could not be listed" in text


# ---- the agent's device tools -------------------------------------------------------------------


def test_the_agent_uses_devices_only_with_the_switch_and_asks_before_acting(tmp_path, monkeypatch):
    from datas.agents import things_tools
    from datas.agents import tools as T

    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    ws = tmp_path / "ws"
    ws.mkdir()
    off = T.ToolContext(workspace=ws)
    names = lambda ctx: {s["function"]["name"] for s in T.schemas(ctx)}  # noqa: E731
    assert not names(off) & set(things_tools.TOOLS)  # not even offered
    assert "May use my camera, screen, printer and other hardware" in T.call(off, "take_photo", {})

    shot = jpeg(1600, 900)
    monkeypatch.setattr(local, "photo", lambda camera=None, fetch=False: b"\xff\xd8JPEG")
    monkeypatch.setattr(local, "screenshot", lambda all_screens=True: shot)
    asked = []
    on = T.ToolContext(
        workspace=ws,
        allow_things=True,
        vision=True,
        ask="risky",
        confirm=lambda t: asked.append(t) or True,
    )
    assert set(things_tools.TOOLS) - {"mouse_keyboard"} <= names(
        on
    ) and "mouse_keyboard" not in names(on)
    out = T.call(on, "take_photo", {})
    assert out.startswith("saved") and asked == ["Take a picture with the camera"]
    assert list((ws / "photos").glob("photo-*.jpg")) and on.images[0]["jpeg"] == b"\xff\xd8JPEG"
    T.call(on, "look_at_screen", {"save_as": "now"})
    assert (ws / "now.jpg").read_bytes() == shot and asked[
        -1
    ] == "Take a picture of what is on your screen"
    assert T.call(on, "look_at_screen", {"save_as": "../outside.jpg"}).startswith("DENIED")
    # listing is free: no question
    monkeypatch.setattr(things, "describe", lambda inv=None: "Cameras: none found")
    n = len(asked)
    assert T.call(on, "list_devices", {}) == "Cameras: none found" and len(asked) == n
    # an AI that cannot see is told so instead of being handed a picture
    blind = T.ToolContext(workspace=ws, allow_things=True, vision=False)
    assert "cannot see pictures" in T.call(blind, "take_photo", {}) and not blind.images
    # a refusal stops the action; the question is in plain words and in the person's language
    questions = []
    no = T.ToolContext(
        workspace=ws,
        allow_things=True,
        ask="risky",
        lang="es",
        confirm=lambda t: questions.append(t) and False,
    )
    assert T.call(no, "mqtt_publish", {"topic": "a/b", "message": "ON"}) == "DENIED by user."
    T.call(no, "home_do", {"service": "light.turn_on", "entity": "light.cocina"})
    T.call(no, "modbus_write", {"device": "caldera", "kind": "coil", "address": 3, "values": [1]})
    T.call(no, "serial_send", {"port": "COM3", "text": "LED ON"})
    T.call(no, "print_file", {"path": "informe.pdf", "copies": 2})
    assert questions == [
        "Enviar a a/b (MQTT): ON",
        "Pedirle a Home Assistant que haga light.turn_on en light.cocina",
        "Escribir [1] en la dirección 3 de caldera (Modbus)",
        "Escribirle a la placa en COM3: LED ON",
        "Imprimir informe.pdf en papel (2 copias)",
    ]
    # problems come back as a sentence
    assert T.call(blind, "mqtt_publish", {"topic": "a/b", "message": "x"}).startswith(
        "could not: No MQTT broker"
    )
    assert T.call(
        blind, "modbus_read", {"device": "boiler", "kind": "holding", "address": 1}
    ).startswith("could not: There is no Modbus device")

    # the mouse and keyboard need their own switch on top
    assert "May use the mouse and keyboard" in T.call(
        blind, "mouse_keyboard", {"action": "click", "x": 1, "y": 1}
    )
    did = []
    monkeypatch.setattr(control, "act", lambda *a, **k: did.append((a, k)) or "Done")
    hands = T.ToolContext(
        workspace=ws,
        allow_things=True,
        allow_control=True,
        vision=True,
        ask="risky",
        confirm=lambda t: asked.append(t) or True,
    )
    assert "mouse_keyboard" in names(hands)
    # no clicking blind: first a look at the screen, and positions are read from that picture
    assert (
        "Look at the screen first"
        in T.call(hands, "mouse_keyboard", {"action": "click", "x": 10, "y": 20})
        and not did
    )
    seen = T.call(hands, "look_at_screen", {})
    assert "The picture is 1600 by 900" in seen and hands.screen_picture == (1600, 900)
    assert T.call(hands, "mouse_keyboard", {"action": "click", "x": 10, "y": 20}) == "Done"
    assert asked[-1] == "Mouse and keyboard — Click at (10, 20)"
    assert did == [(("click", 10, 20, None, None, None), {"picture": (1600, 900)})]
    # typing needs no place on the screen
    assert (
        T.call(
            T.ToolContext(workspace=ws, allow_things=True, allow_control=True),
            "mouse_keyboard",
            {"action": "type", "text": "hola"},
        )
        == "Done"
    )


def test_the_camera_says_when_ffmpeg_is_missing_and_the_agent_fetches_it_only_with_internet(
    tmp_path, monkeypatch
):
    from datas import programs
    from datas.agents import tools as T

    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(programs, "ffmpeg", lambda fetch=False, progress=None: None)
    fetched = []

    def fetch(progress=None):
        fetched.append(1)
        raise RuntimeError("FFmpeg could not be downloaded (offline).")

    monkeypatch.setattr(programs, "fetch_ffmpeg", fetch)
    with pytest.raises(ThingError) as e:
        local.photo(source=PATTERN)
    assert "Tools → Cameras" in str(e.value) and not fetched  # never fetched behind one's back
    ws = tmp_path / "ws"
    ws.mkdir()
    offline = T.ToolContext(workspace=ws, allow_things=True, allow_network=False)
    assert "could not: The camera needs FFmpeg" in T.call(offline, "take_photo", {}) and not fetched
    online = T.ToolContext(workspace=ws, allow_things=True, allow_network=True)
    monkeypatch.setattr(local, "cameras", lambda fetch=False: [{"id": "0", "name": "cam"}])
    assert "could not be downloaded" in T.call(online, "take_photo", {}) and fetched == [1]
    assert things.ffmpeg_state()["found"] is False


def test_pictures_reach_an_ai_that_can_see(tmp_path, monkeypatch):
    """The runner shows a photo to the AI right after the step that took it."""
    from datas.agents import AgentConfig, run_agent
    from datas.agents import runner as R

    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(local, "photo", lambda camera=None, fetch=False: b"\xff\xd8JPEG")
    sent = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            sent.append(list(json["messages"]))  # as it was when sent
            first = len(sent) == 1
            msg = (
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "c1", "function": {"name": "take_photo", "arguments": "{}"}}
                    ],
                }
                if first
                else {"role": "assistant", "content": "I see a test picture."}
            )
            return httpx.Response(200, json={"choices": [{"message": msg}]})

    monkeypatch.setattr(R.httpx, "Client", FakeClient)
    cfg = AgentConfig(
        workspace=tmp_path / "ws", allow_things=True, vision=True, ask="none", use_programs=False
    )
    events = list(run_agent("what does the camera see?", cfg))
    assert events[-1]["type"] == "final" and events[-1]["content"] == "I see a test picture."
    last = sent[1][-1]
    assert last["role"] == "user" and last["content"][1]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )
    assert sent[1][-2]["role"] == "tool"  # the picture comes after the tool's own answer
    # the person sees it too: the agent's window gets the picture as an event
    pics = [e for e in events if e["type"] == "picture"]
    assert (
        len(pics) == 1
        and pics[0]["url"].startswith("data:image/jpeg;base64,")
        and pics[0]["name"].endswith(".jpg")
    )


def test_only_the_newest_pictures_stay_in_the_conversation():
    """A picture takes much of a small AI's working memory; older ones become a line of text."""
    from datas.agents import runner as R

    def pic(n):
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": f"This is the picture {n}."},
                {"type": "image_url", "image_url": {"url": "data:,"}},
            ],
        }

    msgs = [
        {"role": "user", "content": "task"},
        pic(1),
        {"role": "tool", "content": "x"},
        pic(2),
        pic(3),
    ]
    R._forget_old_pictures(msgs, keep=1)
    assert (
        isinstance(msgs[1]["content"], str)
        and "picture 1" in msgs[1]["content"]
        and "no longer shown" in msgs[1]["content"]
    )
    assert isinstance(msgs[3]["content"], str) and isinstance(msgs[4]["content"], list)
    assert msgs[0]["content"] == "task" and msgs[2]["content"] == "x"


# ---- the window's own requests (Tools → Cameras, printers and other hardware) --------------------


@pytest.fixture
def window(tmp_path, monkeypatch):
    """The local service as the window on this computer sees it."""
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    from fastapi.testclient import TestClient

    from datas.server import app as server

    monkeypatch.setattr(server.core.cfg, "lang", "en")
    monkeypatch.setattr(server.core, "window", None)
    return TestClient(server.app, base_url="http://127.0.0.1"), server


def test_the_window_lists_the_hardware_and_takes_pictures(window, monkeypatch):
    client, server = window
    monkeypatch.setattr(local, "cameras", lambda fetch=False: [{"id": "0", "name": "HD Webcam"}])
    monkeypatch.setattr(local, "screens", lambda: [{"id": "all", "width": 1920, "height": 1080}])
    monkeypatch.setattr(local, "printers", lambda: [{"name": "Office", "default": True}])
    monkeypatch.setattr(local, "serial_ports", lambda: [])
    r = client.get("/api/things").json()
    assert r["cameras"][0]["name"] == "HD Webcam" and r["printers"][0]["default"] is True
    assert set(r) >= {
        "cameras",
        "screens",
        "printers",
        "serial",
        "control",
        "ffmpeg",
        "connections",
        "problems",
        "settings",
        "vision",
    }
    assert (
        "password" not in r["settings"]["mqtt"] and r["settings"]["mqtt"]["password_set"] is False
    )
    # a photo comes back ready to be shown or attached to a chat
    monkeypatch.setattr(local, "photo", lambda camera=None: jpeg(640, 360))
    shot = client.post("/api/things/camera/photo", json={"camera": "0"}).json()
    assert shot["image"].startswith("data:image/jpeg;base64,") and (
        shot["width"],
        shot["height"],
    ) == (640, 360)
    # a picture of the screen: Datas' own window steps aside first and comes back afterwards
    did = []

    class Window:
        def hide(self):
            did.append("hide")

        def show(self):
            did.append("show")

    monkeypatch.setattr(local, "screenshot", lambda: did.append("picture") or jpeg(1600, 900))
    monkeypatch.setattr(server.core, "window", Window())
    assert client.get("/api/status").json()["own_window"] is True
    shot = client.post("/api/things/screen", json={"hide": True}).json()
    assert did == ["hide", "picture", "show"] and shot["width"] == 1600
    did.clear()
    client.post("/api/things/screen", json={})  # a test picture from Tools: nothing moves
    assert did == ["picture"]
    # the window comes back even when the picture could not be taken
    did.clear()

    def no_picture():
        raise ThingError("Datas could not look at the screen on this system. ({why})", why="x")

    monkeypatch.setattr(local, "screenshot", no_picture)
    assert client.post("/api/things/screen", json={"hide": True}).status_code == 409
    assert did == ["hide", "show"]


def test_an_answer_is_printed_as_a_pdf_kept_in_the_datas_folder(window, monkeypatch, tmp_path):
    client, server = window  # with DATAS_HOME set, saved files go to <home>/exports
    sent = []

    def fake_print(path, printer=None, copies=1):
        sent.append((path, printer, copies))
        from datas.words import Said

        return Said("Sent {name} to the printer {printer}.", name=path.name, printer="Office")

    monkeypatch.setattr(local, "print_file", fake_print)
    monkeypatch.setattr(local, "answer_format", lambda: "pdf")  # wherever a PDF can be printed
    r = client.post(
        "/api/things/print",
        json={"markdown": "# Lista\n\n- pan\n- leche", "title": "Compras", "copies": 2},
    )
    assert r.status_code == 200, r.text
    path, printer, copies = sent[0]
    assert (
        path.suffix == ".pdf"
        and path.read_bytes().startswith(b"%PDF")
        and copies == 2
        and printer is None
    )
    assert r.json()["said"] == f"Sent {path.name} to the printer Office."
    monkeypatch.setattr(server.core.cfg, "lang", "es")
    r = client.post("/api/things/print", json={"markdown": "hola"})
    assert r.json()["said"].startswith("Se envió ") and r.json()["said"].endswith(
        "a la impresora Office."
    )
    # on a Windows computer without LibreOffice the answer is printed as plain text
    monkeypatch.setattr(local, "answer_format", lambda: "txt")
    client.post("/api/things/print", json={"markdown": "# Lista\n\n- pan\n- leche"})
    plain = sent[-1][0]
    assert plain.suffix == ".txt" and "pan" in plain.read_text(encoding="utf-8")
    # only files Datas itself saved can be printed by path
    assert client.post("/api/things/print", json={"path": "/etc/passwd"}).status_code == 400
    assert client.post("/api/things/print", json={}).status_code == 400


def test_connections_are_saved_and_checked_from_the_window(window):
    client, _server = window
    device = ModbusDevice()
    try:
        r = client.post(
            "/api/things/settings",
            json={
                "modbus": [
                    {"name": "Inverter", "host": "127.0.0.1", "port": device.port, "unit": 3}
                ],
                "home_assistant": {"url": "http://127.0.0.1:9", "token": "T"},
            },
        ).json()
        assert r["modbus"][0]["name"] == "Inverter" and r["home_assistant"] == {
            "url": "http://127.0.0.1:9",
            "token_set": True,
        }
        device.registers[0] = 77
        ok = client.post("/api/things/check", json={"what": "modbus", "name": "inverter"}).json()
        assert ok == {"ok": True, "detail": "Inverter answers; the value at address 0 is 77."}
        del device.registers[0]
        ok = client.post("/api/things/check", json={"what": "modbus", "name": "Inverter"}).json()
        assert ok["ok"] is True and "nothing at address 0" in ok["detail"]
    finally:
        device.close()
    bad = client.post("/api/things/check", json={"what": "home_assistant"}).json()
    assert bad["ok"] is False and bad["detail"].startswith("Could not reach Home Assistant")
    assert (
        client.post("/api/things/check", json={"what": "mqtt"}).json()["ok"] is False
    )  # not set up
    assert client.post("/api/things/check", json={"what": "toaster"}).json()["ok"] is False
    # an empty secret keeps the saved one
    client.post(
        "/api/things/settings",
        json={"home_assistant": {"url": "http://ha.local:8123", "token": ""}},
    )
    assert things.settings()["home_assistant"] == {"url": "http://ha.local:8123", "token": "T"}


@pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX")
def test_the_window_listens_to_a_board(window):
    pytest.importorskip("serial")
    client, _server = window
    board = Board()
    try:
        r = client.post(
            "/api/things/serial", json={"port": board.port, "seconds": 0.6, "baud": 115200}
        )
        assert r.status_code == 200 and "READY v1" in r.json()["text"]
        assert board.got == []  # listening only: nothing was written to the board
    finally:
        board.close()
    r = client.post("/api/things/serial", json={"port": "/dev/ttyNOPE"})
    assert r.status_code == 409 and "Is the board plugged in" in r.json()["detail"]


def test_a_task_that_runs_by_itself_may_use_devices_but_never_the_mouse(
    window, monkeypatch, tmp_path
):
    client, server = window
    from datas.agents import schedule

    t = client.post(
        "/api/agent/tasks",
        json={"title": "Porch", "task": "photo of the porch", "every": "once", "devices": True},
    ).json()
    assert t["devices"] is True and t["allow_shell"] is False
    seen = {}

    def fake_agent(task, cfg):
        seen.update(things=cfg.allow_things, control=cfg.allow_control, shell=cfg.allow_shell)
        yield {"type": "final", "step": 0, "content": "done"}

    import datas.agents as agents

    monkeypatch.setattr(agents, "run_agent", fake_agent)
    monkeypatch.setattr(server.core.server, "running", lambda: True)
    task = server.core.start_scheduler().get(t["id"])
    state, summary, _path = server.core.run_scheduled_task(task)
    assert (state, summary) == ("done", "done")
    assert seen == {"things": True, "control": False, "shell": False}
    # a list written by a newer Datas (a field this version does not know) still loads
    data = json.loads(schedule.tasks_file().read_text(encoding="utf-8"))
    data[0]["from_the_future"] = 1
    data.append({"nonsense": True})
    schedule.tasks_file().write_text(json.dumps(data), encoding="utf-8")
    loaded = schedule.Scheduler.load()
    assert [x.title for x in loaded] == ["Porch"] and loaded[0].devices is True
    client.delete(f"/api/agent/tasks/{t['id']}")
