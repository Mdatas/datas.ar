"""Things plugged into this computer: cameras, the screen, printers, serial ports."""

from __future__ import annotations

import io
import json
import platform
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from datas.things import ThingError
from datas.words import Said

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: do not flash a console


def _run(
    cmd: list[str], timeout: float = 20, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        creationflags=NO_WINDOW,
        env=env,
    )


NEEDS_FFMPEG = (
    "The camera needs FFmpeg, a free program that is not on this computer yet. Get it once "
    "under Tools → Cameras, printers and other hardware."
)


def _ffmpeg(fetch: bool = False, progress=None) -> str:  # noqa: ANN001
    """FFmpeg's path. With ``fetch`` a missing copy is downloaded once and checked (see
    datas.programs.fetch_ffmpeg); without it, a missing copy is an error that says where to
    get it."""
    from datas import programs

    exe = programs.ffmpeg()
    if exe:
        return exe
    if not fetch:
        raise ThingError(NEEDS_FFMPEG)
    try:
        return programs.fetch_ffmpeg(progress)
    except RuntimeError as e:
        raise ThingError("The camera needs FFmpeg. {why}", why=e) from e


# ---------------------------------------------------------------------------
# cameras
# ---------------------------------------------------------------------------


def parse_dshow(text: str) -> list[dict]:
    """Windows: `ffmpeg -list_devices true -f dshow -i dummy` (new and old output styles)."""
    out, section = [], ""
    for line in text.splitlines():
        low = line.lower()
        if "directshow video devices" in low:
            section = "video"
            continue
        if "directshow audio devices" in low:
            section = "audio"
            continue
        m = re.search(r'"([^"]+)"(?:\s+\((video|audio|none)\))?', line)
        if not m or "alternative name" in low:
            continue
        kind = m.group(2) or section
        if kind == "video" and not any(c["name"] == m.group(1) for c in out):
            out.append({"id": m.group(1), "name": m.group(1)})
    return out


def parse_avfoundation(text: str) -> list[dict]:
    """macOS: `ffmpeg -f avfoundation -list_devices true -i ""`."""
    out, video = [], False
    for line in text.splitlines():
        if "AVFoundation video devices" in line:
            video = True
            continue
        if "AVFoundation audio devices" in line:
            video = False
            continue
        m = re.search(r"\[(\d+)\]\s+(.+?)\s*$", line)
        if video and m and "Capture screen" not in m.group(2):
            out.append({"id": m.group(1), "name": m.group(2)})
    return out


def _v4l2() -> list[dict]:
    """Linux: /dev/video*; a camera shows several entries, the first is the picture."""
    out = []
    base = Path("/sys/class/video4linux")
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir(), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
        try:
            if (d / "index").read_text().strip() != "0":
                continue
            name = (d / "name").read_text().strip()
        except OSError:
            continue
        out.append({"id": f"/dev/{d.name}", "name": name})
    return out


def cameras(fetch: bool = False) -> list[dict]:
    system = platform.system()
    if system == "Linux":
        return _v4l2()
    exe = _ffmpeg(fetch)
    if system == "Darwin":
        r = _run([exe, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""])
        return parse_avfoundation(r.stderr + r.stdout)
    r = _run([exe, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"])
    return parse_dshow(r.stderr + r.stdout)


def camera_source(camera: str | None, fetch: bool = False) -> list[str]:
    """The FFmpeg input for a camera of this system (the first one when none is named)."""
    found = cameras(fetch)
    if not found:
        raise ThingError("No camera was found on this computer.")
    pick = next((c for c in found if camera and camera in (c["id"], c["name"])), None)
    if camera and pick is None:
        raise ThingError(
            "There is no camera called {name}. Found: {names}",
            name=repr(camera),
            names=", ".join(c["name"] for c in found),
        )
    cam = pick or found[0]
    system = platform.system()
    if system == "Linux":
        return ["-f", "v4l2", "-i", cam["id"]]
    if system == "Darwin":
        return ["-f", "avfoundation", "-framerate", "30", "-i", cam["id"]]
    return ["-f", "dshow", "-i", f"video={cam['id']}"]


def photo(
    camera: str | None = None,
    source: list[str] | None = None,
    width: int = 1280,
    fetch: bool = False,
    progress=None,  # noqa: ANN001
) -> bytes:
    """One picture from a camera, as JPEG. ``source`` replaces the camera with any FFmpeg
    input (the tests use a test pattern). ``fetch``: get FFmpeg first if it is missing."""
    exe = _ffmpeg(fetch, progress)
    src = source or camera_source(camera)
    with tempfile.TemporaryDirectory(prefix="datas-photo-") as tmp:
        out = Path(tmp) / "photo.jpg"
        # skip the first second: a camera needs a moment to set its exposure
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", *src, "-ss", "1", "-frames:v", "1",
               "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", str(out)]  # fmt: skip
        try:
            r = _run(cmd, timeout=30)
        except subprocess.TimeoutExpired as e:
            raise ThingError(
                "The camera did not answer in time. Is another program using it?"
            ) from e
        if r.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            why = (r.stderr or "").strip().splitlines()[-1:] or ["no picture came out"]
            raise ThingError(
                "Could not take a picture. The camera may be in use by another program, or this "
                "system did not allow Datas to use it. ({why})",
                why=why[0][:160],
            )
        return out.read_bytes()


# ---------------------------------------------------------------------------
# the screen
# ---------------------------------------------------------------------------


def screens() -> list[dict]:
    try:
        from PIL import ImageGrab

        im = ImageGrab.grab()
        return [{"id": "all", "width": im.width, "height": im.height}]
    except Exception:  # noqa: BLE001 - no display, Wayland without a grabber, no permission
        return []


def screenshot(width: int = 1600, all_screens: bool = True) -> bytes:
    """What is on the screen right now, as JPEG (made smaller: an AI reads it better so).
    ``all_screens=False`` gives the main screen only — the one the mouse positions of
    ``datas.things.control`` refer to."""
    try:
        from PIL import ImageGrab

        try:
            im = ImageGrab.grab(all_screens=True) if all_screens else ImageGrab.grab()
        except TypeError:  # older Pillow, or a system without that option
            im = ImageGrab.grab()
    except Exception as e:  # noqa: BLE001
        raise ThingError(
            "Datas could not look at the screen on this system. On Linux this needs an X11 "
            "session or the program gnome-screenshot; on macOS, allow Datas under Privacy → "
            "Screen Recording. ({why})",
            why=f"{type(e).__name__}: {str(e)[:120]}",
        ) from e
    im = im.convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def picture_size(data: bytes) -> tuple[int, int]:
    """Width and height of a picture, in its own dots."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        return im.width, im.height


# ---------------------------------------------------------------------------
# printers
# ---------------------------------------------------------------------------

PRINTS_AS_IS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".ps"}

# Windows has no command that prints a file by itself. This small PowerShell program prints
# plain text (page after page) or one picture with what every Windows has (.NET's
# PrintDocument); what to print comes in through the environment, so no file name or printer
# name is ever pasted into the program's text. Windows PowerShell 5.1 is part of Windows 10/11.
WINDOWS_TEXT = {".txt", ".md", ".csv", ".log", ".srt"}
WINDOWS_PICTURES = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
WINDOWS_PRINT = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$doc = New-Object System.Drawing.Printing.PrintDocument
if ($env:DATAS_PRINTER) { $doc.PrinterSettings.PrinterName = $env:DATAS_PRINTER }
if (-not $doc.PrinterSettings.IsValid) { [Console]::Error.WriteLine("that printer cannot be used"); exit 3 }
$doc.PrinterSettings.Copies = [int16]$env:DATAS_COPIES
if ($env:DATAS_PRINT_TO) {
  $doc.PrinterSettings.PrintToFile = $true
  $doc.PrinterSettings.PrintFileName = $env:DATAS_PRINT_TO
}
$doc.DocumentName = $env:DATAS_PRINT_NAME
$doc.PrintController = New-Object System.Drawing.Printing.StandardPrintController
if ($env:DATAS_PRINT_KIND -eq "picture") {
  $img = [System.Drawing.Image]::FromFile($env:DATAS_PRINT_FILE)
  $doc.add_PrintPage({
    param($sender, $e)
    $m = $e.MarginBounds
    $k = [Math]::Min($m.Width / $img.Width, $m.Height / $img.Height)
    $e.Graphics.DrawImage($img, $m.Left, $m.Top, [int]($img.Width * $k), [int]($img.Height * $k))
    $e.HasMorePages = $false
  })
  $doc.Print()
  $img.Dispose()
} else {
  $script:rest = [System.IO.File]::ReadAllText($env:DATAS_PRINT_FILE, [System.Text.Encoding]::UTF8)
  $font = New-Object System.Drawing.Font("Segoe UI", 11)
  $fmt = [System.Drawing.StringFormat]::GenericTypographic
  $doc.add_PrintPage({
    param($sender, $e)
    $m = $e.MarginBounds
    $size = New-Object System.Drawing.SizeF($m.Width, $m.Height)
    $box = New-Object System.Drawing.RectangleF($m.Left, $m.Top, $m.Width, $m.Height)
    $chars = 0
    $lines = 0
    [void]$e.Graphics.MeasureString($script:rest, $font, $size, $fmt, [ref]$chars, [ref]$lines)
    if ($chars -le 0) { $e.HasMorePages = $false; return }
    $e.Graphics.DrawString($script:rest.Substring(0, $chars), $font, [System.Drawing.Brushes]::Black, $box, $fmt)
    $script:rest = $script:rest.Substring($chars)
    $e.HasMorePages = $script:rest.Length -gt 0
  })
  $doc.Print()
}
"""


def _windows_print(
    path: Path, kind: str, printer: str, copies: int, to_file: Path | None = None
) -> None:
    """Print a text file or a picture on Windows with nothing but Windows itself.
    ``to_file`` sends the result to a file instead of paper (the tests use it with the
    printer "Microsoft Print to PDF")."""
    import base64
    import os

    env = dict(os.environ)
    env.update(
        DATAS_PRINT_FILE=str(path),
        DATAS_PRINT_KIND=kind,
        DATAS_PRINTER=printer or "",
        DATAS_COPIES=str(copies),
        DATAS_PRINT_NAME=path.name,
        DATAS_PRINT_TO=str(to_file) if to_file else "",
    )
    code = base64.b64encode(WINDOWS_PRINT.encode("utf-16-le")).decode()
    try:
        r = _run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", code],
            timeout=180,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ThingError("The printer did not take it: {why}", why=str(e)[:200]) from e
    if r.returncode != 0:
        why = (r.stderr or r.stdout or "").strip().splitlines()
        raise ThingError(
            "The printer did not take it: {why}", why=(why[0] if why else "no answer")[:200]
        )


def answer_format() -> str:
    """The format an answer is turned into before printing: a PDF wherever one can be
    printed without the person installing anything; plain text on a Windows computer that
    has no LibreOffice (Windows cannot print a PDF by itself)."""
    from datas import programs

    if platform.system() == "Windows" and not programs.find("libreoffice"):
        return "txt"
    return "pdf"


def parse_lpstat(names: str, default: str) -> list[dict]:
    m = re.search(r":\s*(\S+)\s*$", default.strip()) if default.strip() else None
    dflt = m.group(1) if m else ""
    return [{"name": n, "default": n == dflt} for n in (x.strip() for x in names.splitlines()) if n]


def printers() -> list[dict]:
    if platform.system() == "Windows":
        r = _run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Printer | Select-Object Name,Default | ConvertTo-Json -Compress"],
            timeout=25,
        )  # fmt: skip
        try:
            data = json.loads(r.stdout or "[]")
        except ValueError:
            return []
        data = [data] if isinstance(data, dict) else data
        return [
            {"name": str(p.get("Name")), "default": bool(p.get("Default"))}
            for p in data
            if p.get("Name")
        ]
    if not shutil.which("lpstat"):
        return []
    return parse_lpstat(_run(["lpstat", "-e"]).stdout, _run(["lpstat", "-d"]).stdout)


def print_file(
    path: Path, printer: str | None = None, copies: int = 1, to_file: Path | None = None
) -> str:
    """Send a file to a printer. Returns one sentence saying what was done. ``to_file``
    (Windows, text and pictures only) is for the tests."""
    from datas import programs

    path = Path(path)
    if not path.is_file():
        raise ThingError("There is no file {name} to print.", name=path.name)
    copies = max(1, min(int(copies or 1), 20))
    known = printers()
    if not known:
        raise ThingError("No printer is set up on this computer.")
    if printer and not any(p["name"] == printer for p in known):
        raise ThingError(
            "There is no printer called {name}. Found: {names}",
            name=repr(printer),
            names=", ".join(p["name"] for p in known),
        )
    target = printer or next((p["name"] for p in known if p["default"]), known[0]["name"])
    office = programs.find("libreoffice")

    if platform.system() == "Windows":
        if office:
            r = _run([office, "--headless", "--pt", target, str(path)], timeout=180)
            if r.returncode != 0:
                raise ThingError(
                    "LibreOffice could not print it: {why}",
                    why=(r.stderr or r.stdout).strip()[:200],
                )
            return Said("Sent {name} to the printer {printer}.", name=path.name, printer=target)
        ext = path.suffix.lower()
        if ext in WINDOWS_TEXT or ext in WINDOWS_PICTURES:
            kind = "picture" if ext in WINDOWS_PICTURES else "text"
            _windows_print(path, kind, target, copies, to_file)
            if copies > 1:
                return Said(
                    "Sent {name} to the printer {printer}, {copies} copies.",
                    name=path.name,
                    printer=target,
                    copies=copies,
                )
            return Said("Sent {name} to the printer {printer}.", name=path.name, printer=target)
        if printer and not next((p for p in known if p["name"] == printer and p["default"]), None):
            raise ThingError(
                "Without LibreOffice, Datas can only print to the default printer on Windows. "
                "Install LibreOffice (free) or make that printer the default."
            )
        ps = f"Start-Process -FilePath '{str(path).replace(chr(39), chr(39) * 2)}' -Verb Print"
        r = _run(["powershell", "-NoProfile", "-Command", ps], timeout=60)
        if r.returncode != 0:
            raise ThingError(
                "Windows has no program that can print this kind of file by itself. "
                "Install LibreOffice (free) and try again."
            )
        return Said("Asked Windows to print {name} on the default printer.", name=path.name)

    if not shutil.which("lp"):
        raise ThingError("This system has no printing service (CUPS).")
    send = path
    tmp = None
    if path.suffix.lower() not in PRINTS_AS_IS:
        if not office:
            raise ThingError(
                "A {kind} file has to become a PDF before it can be printed, and that needs "
                "LibreOffice (free). Save it as PDF, or install LibreOffice.",
                kind=path.suffix,
            )
        tmp = tempfile.mkdtemp(prefix="datas-print-")
        r = _run(
            [office, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(path)], timeout=180
        )
        send = Path(tmp) / (path.stem + ".pdf")
        if r.returncode != 0 or not send.is_file():
            shutil.rmtree(tmp, ignore_errors=True)
            raise ThingError("LibreOffice could not turn that file into a PDF to print it.")
    try:
        r = _run(["lp", "-d", target, "-n", str(copies), str(send)], timeout=60)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0:
        raise ThingError(
            "The printer did not take it: {why}", why=(r.stderr or r.stdout).strip()[:200]
        )
    if copies > 1:
        return Said(
            "Sent {name} to the printer {printer}, {copies} copies.",
            name=path.name,
            printer=target,
            copies=copies,
        )
    return Said("Sent {name} to the printer {printer}.", name=path.name, printer=target)


# ---------------------------------------------------------------------------
# serial ports: Arduino and other boards, 3D printers, instruments
# ---------------------------------------------------------------------------

# Who made the USB part of a board (USB vendor numbers), in words a person recognises.
USB_MAKERS = {
    0x2341: "Arduino board",
    0x2A03: "Arduino board",
    0x1A86: "board with a CH340 USB chip (many Arduino-compatible and ESP boards)",
    0x10C4: "board with a CP210x USB chip (many ESP32 boards)",
    0x0403: "FTDI USB-serial adapter",
    0x303A: "Espressif board (ESP32)",
    0x2E8A: "Raspberry Pi Pico",
    0x0483: "STMicroelectronics board",
    0x16C0: "Teensy or a similar board",
    0x0D28: "micro:bit or an Arm Mbed board",
    0x239A: "Adafruit board",
    0x1B4F: "SparkFun board",
}


def serial_ports() -> list[dict]:
    try:
        from serial.tools import list_ports
    except ImportError as e:
        raise ThingError(
            "The serial-port part (pyserial) is missing from this copy of Datas."
        ) from e
    out = []
    for p in sorted(list_ports.comports(), key=lambda p: p.device):
        if p.vid is None and "ttyS" in p.device:
            continue  # built-in ports of the motherboard that nothing is plugged into
        what = USB_MAKERS.get(p.vid or -1) or p.description or p.manufacturer or "serial device"
        if what in ("n/a", ""):
            what = "serial device"
        out.append(
            {
                "port": p.device,
                "what": what,
                "description": p.description if p.description != "n/a" else "",
                "maker": p.manufacturer or "",
                "usb": f"{p.vid:04x}:{p.pid:04x}"
                if p.vid is not None and p.pid is not None
                else "",
            }
        )
    return out


def serial_talk(
    port: str,
    send: str | None = None,
    seconds: float = 3.0,
    baud: int = 9600,
    settle: float | None = None,
    limit: int = 20000,
) -> str:
    """Open a serial port, optionally write a line, and return what the device says during
    ``seconds``. Opening the port restarts most Arduino boards, so before writing we wait
    ``settle`` seconds (2 by default) for the board to be ready."""
    try:
        import serial
    except ImportError as e:
        raise ThingError(
            "The serial-port part (pyserial) is missing from this copy of Datas."
        ) from e
    seconds = max(0.2, min(float(seconds), 60.0))
    try:
        with serial.Serial(port, int(baud), timeout=0.2, write_timeout=5) as s:
            got = b""
            if send is not None:
                wait = 2.0 if settle is None else max(0.0, min(float(settle), 10.0))
                end = time.time() + wait
                while time.time() < end:  # read the board's greeting while it starts
                    got += s.read(4096)
                # write() waits at most write_timeout; no flush() here, which would wait
                # without a limit on a device that stopped taking data
                s.write(send.encode("utf-8") + (b"" if send.endswith("\n") else b"\n"))
            end = time.time() + seconds
            while time.time() < end and len(got) < limit:
                got += s.read(4096)
    except (OSError, ValueError) as e:  # serial.SerialException is an OSError
        raise ThingError(
            "Could not use {port}: {why}. Is the board plugged in, and is another program "
            "(the Arduino program's serial monitor, for example) using it?",
            port=port,
            why=str(e),
        ) from e
    return got[:limit].decode("utf-8", "replace")
