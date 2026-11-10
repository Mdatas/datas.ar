"""Open programs already on this computer that the AI's agent can work with.

Datas does not replace the tools people use — it finds them and lets the agent drive them:
convert a Word file to PDF with LibreOffice, export a drawing with Inkscape, turn an OpenSCAD
model into a printable STL, cut a video with FFmpeg, open a result in the program it belongs
to. Nothing is installed behind the user's back: a program that is not there is shown with
the address of its official site.

Three levels, from simplest to deepest:

1. **Convert** — ``convert(src, "pdf")`` picks whichever installed program can do it (and
   Datas itself for Markdown → Word/Excel/PowerPoint/PDF and for reading documents as text).
2. **Run** — the agent may run one of the programs listed here with arguments (never an
   arbitrary command; asks first unless the user chose otherwise).
3. **Tools inside the program (MCP)** — programs that speak the Model Context Protocol expose
   their own operations to the agent. The ArtCraft "Craft" apps do: PdfCraft's
   ``pdfcraft-cli mcp --root <folder>`` is wired from its documentation; the other Craft apps
   are tried the same way, as their site says every app can be driven from a CLI, a JSON
   control channel or an MCP server.
"""

from __future__ import annotations

import glob
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

from datas.config import home
from datas.words import Problem

SYSTEM = platform.system()  # Windows | Darwin | Linux


def _p(en: str, es: str) -> dict:
    return {"en": en, "es": es}


# name(s) to look for on PATH, then typical install locations per system (globs allowed)
PROGRAMS: list[dict] = [
    {
        "id": "libreoffice",
        "name": "LibreOffice",
        "group": "office",
        "site": "https://www.libreoffice.org",
        "names": ["soffice", "libreoffice"],
        "paths": {
            "Windows": [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            ],
            "Darwin": ["/Applications/LibreOffice.app/Contents/MacOS/soffice"],
            "Linux": [
                "/usr/bin/soffice",
                "/usr/lib/libreoffice/program/soffice",
                "/snap/bin/libreoffice",
                "/opt/libreoffice*/program/soffice",
            ],
        },
        "does": _p(
            "Opens, edits and converts Word, Excel, PowerPoint and OpenDocument files; turns any of them into PDF.",
            "Abre, edita y convierte archivos de Word, Excel, PowerPoint y OpenDocument; pasa cualquiera a PDF.",
        ),
    },
    {
        "id": "pandoc",
        "name": "Pandoc",
        "group": "office",
        "site": "https://pandoc.org",
        "names": ["pandoc"],
        "paths": {
            "Windows": [r"C:\Program Files\Pandoc\pandoc.exe", r"%LOCALAPPDATA%\Pandoc\pandoc.exe"],
            "Darwin": ["/opt/homebrew/bin/pandoc", "/usr/local/bin/pandoc"],
        },
        "does": _p(
            "Converts between text formats: Markdown, Word, web page, e-book (EPUB), LaTeX.",
            "Convierte entre formatos de texto: Markdown, Word, página web, libro electrónico (EPUB), LaTeX.",
        ),
    },
    {
        "id": "ffmpeg",
        "name": "FFmpeg",
        "group": "media",
        "site": "https://ffmpeg.org",
        "names": ["ffmpeg"],
        "paths": {"Darwin": ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]},
        "does": _p(
            "Converts, cuts and joins video and audio; extracts the sound of a video.",
            "Convierte, corta y une video y audio; extrae el sonido de un video.",
        ),
    },
    {
        "id": "imagemagick",
        "name": "ImageMagick",
        "group": "media",
        "site": "https://imagemagick.org",
        "names": ["magick"],
        "paths": {
            "Windows": [r"C:\Program Files\ImageMagick-*\magick.exe"],
            "Darwin": ["/opt/homebrew/bin/magick", "/usr/local/bin/magick"],
        },
        "does": _p(
            "Converts and resizes pictures in bulk, between almost every image format.",
            "Convierte y redimensiona imágenes en lote, entre casi todos los formatos.",
        ),
    },
    {
        "id": "inkscape",
        "name": "Inkscape",
        "group": "design",
        "site": "https://inkscape.org",
        "names": ["inkscape"],
        "paths": {
            "Windows": [r"C:\Program Files\Inkscape\bin\inkscape.exe"],
            "Darwin": ["/Applications/Inkscape.app/Contents/MacOS/inkscape"],
            "Linux": ["/usr/bin/inkscape", "/snap/bin/inkscape"],
        },
        "does": _p(
            "Vector drawing (logos, diagrams, plans). Exports SVG drawings to PNG or PDF.",
            "Dibujo vectorial (logos, diagramas, planos). Exporta dibujos SVG a PNG o PDF.",
        ),
    },
    {
        "id": "gimp",
        "name": "GIMP",
        "group": "design",
        "site": "https://www.gimp.org",
        "names": ["gimp", "gimp-3.0", "gimp-2.10"],
        "paths": {
            "Windows": [
                r"C:\Program Files\GIMP 3\bin\gimp-3*.exe",
                r"C:\Program Files\GIMP 2\bin\gimp-2*.exe",
            ],
            "Darwin": ["/Applications/GIMP.app/Contents/MacOS/gimp"],
        },
        "does": _p("Photo and image editing.", "Edición de fotos e imágenes."),
    },
    {
        "id": "krita",
        "name": "Krita",
        "group": "design",
        "site": "https://krita.org",
        "names": ["krita"],
        "paths": {
            "Windows": [r"C:\Program Files\Krita (x64)\bin\krita.exe"],
            "Darwin": ["/Applications/krita.app/Contents/MacOS/krita"],
        },
        "does": _p("Digital painting and illustration.", "Pintura digital e ilustración."),
    },
    {
        "id": "blender",
        "name": "Blender",
        "group": "3d",
        "site": "https://www.blender.org",
        "names": ["blender"],
        "paths": {
            "Windows": [r"C:\Program Files\Blender Foundation\Blender *\blender.exe"],
            "Darwin": ["/Applications/Blender.app/Contents/MacOS/Blender"],
            "Linux": ["/usr/bin/blender", "/snap/bin/blender"],
        },
        "does": _p(
            "3D modelling, animation and rendering; can run scripts without opening its window.",
            "Modelado 3D, animación y render; puede ejecutar scripts sin abrir su ventana.",
        ),
    },
    {
        "id": "openscad",
        "name": "OpenSCAD",
        "group": "3d",
        "site": "https://openscad.org",
        "names": ["openscad"],
        "paths": {
            "Windows": [
                r"C:\Program Files\OpenSCAD\openscad.exe",
                r"C:\Program Files\OpenSCAD*\openscad.exe",
            ],
            "Darwin": [
                "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
                "/Applications/OpenSCAD*.app/Contents/MacOS/OpenSCAD",
            ],
            "Linux": ["/usr/bin/openscad", "/snap/bin/openscad"],
        },
        "does": _p(
            "Turns a written 3D model (.scad, what the 3D-printing helper produces) into a printable STL or 3MF file.",
            "Convierte un modelo 3D escrito (.scad, lo que produce el ayudante de impresión 3D) en un archivo STL o 3MF para imprimir.",
        ),
    },
    {
        "id": "freecad",
        "name": "FreeCAD",
        "group": "3d",
        "site": "https://www.freecad.org",
        "names": ["freecadcmd", "FreeCADCmd", "freecad", "FreeCAD"],
        "paths": {
            "Windows": [
                r"C:\Program Files\FreeCAD*\bin\FreeCADCmd.exe",
                r"C:\Program Files\FreeCAD*\bin\freecadcmd.exe",
            ],
            "Darwin": [
                "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd",
                "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD",
            ],
            "Linux": ["/usr/bin/freecadcmd", "/usr/bin/freecad", "/snap/bin/freecad"],
        },
        "does": _p(
            "Parametric CAD for mechanical parts and architecture; runs Python scripts for batch work.",
            "CAD paramétrico para piezas mecánicas y arquitectura; ejecuta scripts de Python para trabajo en lote.",
        ),
    },
    {
        "id": "tesseract",
        "name": "Tesseract OCR",
        "group": "office",
        "site": "https://github.com/tesseract-ocr/tesseract",
        "names": ["tesseract"],
        "paths": {
            "Windows": [r"C:\Program Files\Tesseract-OCR\tesseract.exe"],
            "Darwin": ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"],
        },
        "does": _p(
            "Reads the text in a scanned page or a photo (OCR, optical character recognition).",
            "Lee el texto de una página escaneada o una foto (OCR, reconocimiento óptico de caracteres).",
        ),
    },
]

# The ArtCraft "Craft" apps (getartcraft.com/apps), free and open source (MIT or Apache-2.0).
# What each is comes from that page; most are early versions. Only PdfCraft's command names
# were read from its own documentation; the others are looked for under the same pattern.
CRAFT_SITE = "https://getartcraft.com/apps"
CRAFT_LAUNCHER = "https://github.com/storytold/craft-launcher/releases/latest"
CRAFT_APPS: list[dict] = [
    {
        "id": "pdfcraft",
        "name": "PdfCraft",
        "verified": True,
        "does": _p(
            "Read, organise, combine, split and protect PDFs.",
            "Leer, ordenar, unir, dividir y proteger PDF.",
        ),
    },
    {"id": "photocraft", "name": "PhotoCraft", "does": _p("Image editor.", "Editor de imágenes.")},
    {
        "id": "vectorcraft",
        "name": "VectorCraft",
        "does": _p("Vector illustration.", "Ilustración vectorial."),
    },
    {"id": "filmcraft", "name": "FilmCraft", "does": _p("Video editor.", "Editor de video.")},
    {
        "id": "lightcraft",
        "name": "LightCraft",
        "does": _p("Photo library and raw developer.", "Biblioteca de fotos y revelado raw."),
    },
    {
        "id": "effectcraft",
        "name": "EffectCraft",
        "does": _p(
            "Motion graphics and visual effects.", "Gráficos en movimiento y efectos visuales."
        ),
    },
    {
        "id": "designcraft",
        "name": "DesignCraft",
        "does": _p("Page layout and publishing.", "Maquetación y publicación."),
    },
    {
        "id": "figcraft",
        "name": "FigCraft",
        "does": _p("Interface design and prototyping.", "Diseño de interfaces y prototipos."),
    },
    {
        "id": "texturecraft",
        "name": "TextureCraft",
        "does": _p("3D texture painting.", "Pintura de texturas 3D."),
    },
    {
        "id": "materialcraft",
        "name": "MaterialCraft",
        "does": _p("Procedural materials (nodes).", "Materiales procedurales (nodos)."),
    },
    {
        "id": "wordcraft",
        "name": "WordCraft",
        "does": _p("Word processor.", "Procesador de textos."),
    },
    {
        "id": "soundcraft",
        "name": "SoundCraft",
        "does": _p("Audio recording, editing and mixing.", "Grabación, edición y mezcla de audio."),
    },
    {"id": "deckcraft", "name": "DeckCraft", "does": _p("Slide presentations.", "Presentaciones.")},
    {
        "id": "cadcraft",
        "name": "CADCraft",
        "does": _p("CAD and drafting.", "CAD y dibujo técnico."),
    },
    {
        "id": "gridcraft",
        "name": "GridCraft",
        "does": _p("Spreadsheets and data analysis.", "Planillas y análisis de datos."),
    },
]


def _expand(pattern: str) -> list[str]:
    return sorted(glob.glob(os.path.expandvars(os.path.expanduser(pattern))), reverse=True)


def _find(names: list[str], paths: list[str]) -> str | None:
    for n in names:
        w = shutil.which(n)
        if w:
            return w
    for pat in paths:
        for hit in _expand(pat):
            if os.path.isfile(hit):
                return hit
    return None


def _craft_paths(app: dict, cli: bool) -> tuple[list[str], list[str]]:
    exe = app["id"] + ("-cli" if cli else "")
    name = app["name"]
    if SYSTEM == "Windows":
        return [exe + ".exe", exe], [
            rf"C:\Program Files\{name}\{exe}.exe",
            rf"%LOCALAPPDATA%\Programs\{name}\{exe}.exe",
        ]
    if SYSTEM == "Darwin":
        return [exe], [
            f"/Applications/{name}.app/Contents/MacOS/{exe}",
            f"/usr/local/bin/{exe}",
            f"/opt/homebrew/bin/{exe}",
        ]
    return [exe], [
        f"/usr/bin/{exe}",
        f"/usr/local/bin/{exe}",
        f"~/Applications/{exe}",
        f"~/.local/bin/{exe}",
    ]


# ---------------------------------------------------------------------------
# What the agent may hand to a found program while "may run commands" is off
# ---------------------------------------------------------------------------
# The agent uses these programs to open, convert and export. Three things would turn
# ``run_program`` into a side door, so they are refused unless the user allowed commands:
#   * options and files that make a program run a script or start another program;
#   * network addresses, when internet is off (or inside the user's own network);
#   * files and folders outside the ones the user gave the agent.
# A list like this cannot be complete: it closes the well-known doors, and ``run_program``
# still asks first by default. Programs the user listed in programs.json are theirs to
# decide about and are not filtered.
SCRIPT_OPTIONS: dict[str, tuple[str, ...]] = {
    "blender": ("-P", "--python", "--python-expr", "--python-text", "--python-console",
                "--addons", "-y", "--enable-autoexec"),
    "freecad": ("-c", "--run-test", "--response-file"),
    "gimp": ("-b", "--batch", "--batch-interpreter"),
    "pandoc": ("-F", "--filter", "-L", "--lua-filter", "--pdf-engine", "--pdf-engine-opt"),
    "imagemagick": ("-script",),
    "inkscape": ("--shell",),
}  # fmt: skip
SCRIPT_ENDINGS = (".py", ".fcmacro", ".scm", ".lua", ".msl", ".bat", ".cmd", ".ps1", ".sh", ".vbs")
# LibreOffice macro addresses, ImageMagick scripts and pipes, files of arguments (@file),
# LibreOffice start-up variables (-env:…, which can point it at another profile)
SCRIPT_STARTS = ("macro:", "vnd.sun.star.script:", "msl:", "|", "@", "-env:")


def _is_user_program(pid: str) -> bool:
    return any(u["id"] == pid for u in user_programs())


def _option_runs_code(text: str, options: tuple[str, ...]) -> bool:
    opt = text.split("=", 1)[0]
    if opt.startswith("--"):
        low = opt.lower()
        # programs such as pandoc accept a long option cut short (--lua-f): refuse any
        # beginning of a refused option too
        return low in options or (
            len(low) >= 4 and any(o.startswith("--") and o.startswith(low) for o in options)
        )
    if not opt.startswith("-") or len(opt) < 2:
        return False
    if opt in options:  # exact; case matters (Blender: -P runs Python, -p places the window)
        return True
    letters = [o[1] for o in options if len(o) == 2]
    if opt[1] in letters:  # value written right after the letter: -Pscript, -Ffilter
        return True
    return len(opt) <= 4 and any(ch in letters for ch in opt[1:])  # letters grouped: -ib


def runs_code(pid: str, arguments: list[str]) -> str | None:
    """The first argument that would make program ``pid`` run a script or another program,
    or None."""
    if _is_user_program(pid):
        return None
    options = SCRIPT_OPTIONS.get(pid, ())
    for a in arguments:
        text = str(a).strip()
        if _option_runs_code(text, options):
            return text
        low = text.lower()
        if low.startswith(SCRIPT_STARTS) or low.endswith(SCRIPT_ENDINGS):
            return text
    return None


_ADDRESS = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]+://[^\s\"'<>|]*")


def network_addresses(arguments: list[str]) -> list[str]:
    """Addresses of the form ``scheme://host…`` inside the arguments (web pages, streams,
    shared folders). ``file:///path`` and Blender's ``//relative`` paths name no host and are
    not network addresses."""
    out: list[str] = []
    for a in arguments:
        for m in _ADDRESS.finditer(str(a)):
            try:
                host = urlsplit(m.group(0)).netloc
            except ValueError:
                host = "?"
            if host:
                out.append(m.group(0))
    return out


NOT_FILES = {"-", "/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "nul", "con"}


def outside_paths(pid: str, arguments: list[str], roots: list[Path], cwd: Path) -> list[str]:
    """Arguments that name a file or folder outside ``roots`` (the folders the agent may use).
    An argument counts when, read as a path — a relative one starts from ``cwd`` — it lands
    outside those folders on something that exists, or in a folder that exists."""
    if _is_user_program(pid):
        return []
    roots = [r.resolve() for r in roots]
    out: list[str] = []
    for a in arguments:
        text = str(a).strip()
        if "://" in text:  # an address, not a path (see network_addresses)
            continue
        value = text.split("=", 1)[1] if "=" in text else ""
        candidates = [value] if text.startswith("-") else [text, value]
        for c in candidates:
            c = c.strip().strip("\"'")
            if not c or c.lower() in NOT_FILES:
                continue
            if pid == "blender" and c.startswith("//"):  # Blender: "next to the .blend file"
                continue
            # "0:a", "00:01:00", "640:480": stream names, times and sizes, not files. (A
            # letter and a colon — "D:notes.txt" — is a Windows drive and is checked.)
            if ":" in c and not re.search(r"[\\/]", c) and not re.match(r"[A-Za-z]:", c):
                continue
            try:
                p = Path(os.path.expanduser(c))
                p = (p if p.is_absolute() else cwd / p).resolve()
                if any(p == r or r in p.parents for r in roots):
                    continue
                real = p.exists() or p.parent.is_dir()
            except (OSError, ValueError, RuntimeError):
                continue
            if real:
                out.append(text)
                break
    return out


def user_programs() -> list[dict]:
    """Programs the user added by hand: ``<data>/programs.json`` =
    ``[{"id": "myprog", "name": "My program", "path": "/path/to/it", "does": "what it is for"}]``"""
    import json

    try:
        d = json.loads((home() / "programs.json").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    out = []
    for x in d if isinstance(d, list) else []:
        if isinstance(x, dict) and x.get("id") and x.get("path") and os.path.isfile(str(x["path"])):
            out.append(
                {
                    "id": str(x["id"]),
                    "name": str(x.get("name") or x["id"]),
                    "group": "yours",
                    "site": "",
                    "path": str(x["path"]),
                    "found": True,
                    "does": _p(str(x.get("does", "")), str(x.get("does", ""))),
                }
            )
    return out


def detect() -> list[dict]:
    """Every known program with ``found`` and ``path`` (no program is started to find out)."""
    out = []
    for p in PROGRAMS:
        path = _find(p["names"], p.get("paths", {}).get(SYSTEM, []))
        if not path and p["id"] == "ffmpeg":
            path = ffmpeg_fetched()  # the copy Datas fetched (see fetch_ffmpeg)
        out.append(
            {k: p[k] for k in ("id", "name", "group", "site", "does")}
            | {"found": bool(path), "path": path}
        )
    for a in CRAFT_APPS:
        gui = _find(*_craft_paths(a, cli=False))
        cli = _find(*_craft_paths(a, cli=True))
        out.append(
            {
                "id": a["id"],
                "name": a["name"],
                "group": "artcraft",
                "site": CRAFT_SITE,
                "does": a["does"],
                "found": bool(gui or cli),
                "path": gui or cli,
                "cli": cli,
                "agent_tools": bool(cli),
                "verified": bool(a.get("verified")),
            }
        )
    return out + user_programs()


def find(pid: str) -> str | None:
    """Path of an installed program by id (for ``ffmpeg`` also the copy Datas fetched)."""
    for p in detect():
        if p["id"] == pid and p.get("found"):
            return p.get("cli") if p.get("group") == "artcraft" and p.get("cli") else p["path"]
    return None


# ---------------------------------------------------------------------------
# FFmpeg: the system's copy, or one fetched once and checked
# ---------------------------------------------------------------------------
# FFmpeg reads and writes almost every sound and video format, and reads cameras. Linux
# usually has it; Windows and macOS do not. When it is missing, Datas fetches a ready-made
# build once into <data>/programs/ffmpeg and uses that copy.
#
# The builds are the ones the open-source project static-ffmpeg uses (folder v8.0 of
# github.com/zackees/ffmpeg_bins). Its workflow takes them from the builders that
# ffmpeg.org links to: BtbN (Linux), gyan.dev (Windows), evermeet.cx (macOS Intel) and
# osxexperts.net (macOS Apple Silicon). The address is pinned to one commit and each file is
# checked against the size and SHA-256 recorded in that commit (its Git LFS pointer), so a
# changed or damaged file is refused.
FFMPEG_REPO = "https://github.com/zackees/ffmpeg_bins"
FFMPEG_COMMIT = "df95abcb0ce6efff710dda5ef28a2f6f1dc21493"
FFMPEG_BUILDS: dict[str, tuple[int, str]] = {  # key -> (bytes, sha256) of v8.0/<key>.zip
    "win32": (72065209, "92662c2241e93fe71b3f3a01e94a0b0dc8cfad726019f96b83bc109ce44c5d0b"),
    "darwin": (53079896, "70fd5b21cb37b6ea97c8b584cf76b3cc6a90179831c9c269811b9716c28605fb"),
    "darwin_arm64": (
        41925556,
        "b2da44a8169c4d09a97db996250690c3346f72e4795521d23d3dbb1e72421207",
    ),
    "linux": (142008975, "ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad"),
    "linux_arm64": (
        131816005,
        "e03efe471c03b999f10988d5db62ae3bd94837463291b3c7755528b100e97d6f",
    ),
}
_ffmpeg_lock = threading.Lock()


def ffmpeg_key(system: str | None = None, machine: str | None = None) -> str | None:
    """Which of the builds fits this computer (None: there is none for it)."""
    system = system or SYSTEM
    arm = (machine or platform.machine()).lower() in ("arm64", "aarch64")
    if system == "Windows":
        return None if arm else "win32"
    if system == "Darwin":
        return "darwin_arm64" if arm else "darwin"
    if system == "Linux":
        return "linux_arm64" if arm else "linux"
    return None


def ffmpeg_dir() -> Path:
    return home() / "programs" / "ffmpeg"


def ffmpeg_fetched() -> str | None:
    """The copy Datas fetched earlier, if it is there."""
    key = ffmpeg_key()
    if not key:
        return None
    exe = ffmpeg_dir() / key / ("ffmpeg.exe" if SYSTEM == "Windows" else "ffmpeg")
    return str(exe) if exe.is_file() and (ffmpeg_dir() / key / "checked").is_file() else None


def ffmpeg_download() -> dict | None:
    """What would be fetched for this computer: {"url", "bytes", "sha256"}."""
    key = ffmpeg_key()
    if not key or key not in FFMPEG_BUILDS:
        return None
    size, sha = FFMPEG_BUILDS[key]
    return {
        "url": f"{FFMPEG_REPO}/raw/{FFMPEG_COMMIT}/v8.0/{key}.zip",
        "bytes": size,
        "sha256": sha,
        "key": key,
    }


def fetch_ffmpeg(progress=None, source: str | None = None) -> str:  # noqa: ANN001
    """Download the build for this computer, check it and unpack it. Returns the program's
    path. ``progress(done, total)`` is called while downloading; ``source`` replaces the
    address in the tests. Raises a Problem (a RuntimeError) with a sentence for the person."""
    import zipfile

    import httpx

    from datas.runtime.llamacpp import _download

    with _ffmpeg_lock:
        have = ffmpeg_fetched()
        if have:
            return have
        dl = ffmpeg_download()
        if not dl:
            raise Problem(
                "There is no ready-made FFmpeg for this kind of computer. Install it from "
                "https://ffmpeg.org (or with your system's package manager)."
            )
        base = ffmpeg_dir()
        base.mkdir(parents=True, exist_ok=True)
        zip_path = base / (dl["key"] + ".zip")
        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, read=120)) as c:
                _download(source or dl["url"], zip_path, c, progress, "sha256:" + dl["sha256"])
        except ValueError as e:  # the checksum did not match: the file is already deleted
            raise Problem(
                "The FFmpeg file that arrived is not the one Datas expects, so it was not "
                "used. Try again later, or install FFmpeg from https://ffmpeg.org."
            ) from e
        except (httpx.HTTPError, OSError) as e:
            raise Problem(
                "FFmpeg could not be downloaded ({why}). Check the connection and try again, "
                "or install FFmpeg from https://ffmpeg.org.",
                why=str(e),
            ) from e
        target = base / dl["key"]
        names = {"ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"}
        try:
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True)
            with zipfile.ZipFile(zip_path) as z:
                for info in z.infolist():
                    # only the two programs, by their bare names: nothing in the archive can
                    # choose where it lands
                    name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
                    if info.is_dir() or name not in names:
                        continue
                    with z.open(info) as src, (target / name).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    if SYSTEM != "Windows":
                        os.chmod(target / name, 0o755)
        except (OSError, zipfile.BadZipFile) as e:
            shutil.rmtree(target, ignore_errors=True)
            raise Problem("FFmpeg arrived but could not be unpacked: {why}", why=str(e)) from e
        finally:
            zip_path.unlink(missing_ok=True)
        exe = target / ("ffmpeg.exe" if SYSTEM == "Windows" else "ffmpeg")
        if not exe.is_file():
            shutil.rmtree(target, ignore_errors=True)
            raise Problem("The FFmpeg download did not contain the program.")
        (target / "checked").write_text(f"{dl['url']}\nsha256 {dl['sha256']}\n", encoding="utf-8")
        return str(exe)


def ffmpeg(fetch: bool = False, progress=None) -> str | None:  # noqa: ANN001
    """FFmpeg's path: the system's copy, else the one Datas fetched, else (with ``fetch``)
    fetch it now. None when there is none and it could not be fetched."""
    exe = find("ffmpeg")  # detect() already looks at the fetched copy
    if exe or not fetch:
        return exe
    try:
        return fetch_ffmpeg(progress)
    except RuntimeError:
        return None


def craft_mcp_servers() -> dict[str, dict]:
    """MCP entries for the Craft apps whose command-line tool is installed."""
    out = {}
    for p in detect():
        if p.get("group") == "artcraft" and p.get("cli"):
            out[p["id"]] = {
                "command": p["cli"],
                "args": ["mcp", "--compact", "--root", "{root}"]
                if p.get("verified")
                else ["mcp", "--root", "{root}"],
                "env": {},
                "source": "artcraft",
            }
    return out


def artcraft_launcher_asset() -> dict:
    """The ArtCraft Launcher installer for this computer, from the project's newest release,
    with the checksum from the SHA256SUMS.txt published beside it. File names follow the
    patterns in the launcher's README. Raises RuntimeError (with the page to visit) when the
    release cannot be read."""
    import httpx

    api = "https://api.github.com/repos/storytold/craft-launcher/releases/latest"
    try:
        r = httpx.get(
            api,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "datas.ar", "Accept": "application/vnd.github+json"},
        )
        r.raise_for_status()
        rel = r.json()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"The release list could not be read ({e}). Get the launcher at {CRAFT_LAUNCHER}"
        ) from e
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if SYSTEM == "Windows":
        want = ["-windows-arm64.msi"] if arm else ["-windows-x64.msi"]
    elif SYSTEM == "Darwin":
        want = ["-macos-universal.dmg"]
    else:
        cpu = "aarch64" if arm else "x86_64"
        deb = Path("/etc/debian_version").exists()
        want = (
            [f"-linux-{cpu}.deb", f"-linux-{cpu}.AppImage"] if deb else [f"-linux-{cpu}.AppImage"]
        )
    assets = rel.get("assets") or []
    pick = next(
        (
            a
            for w in want
            for a in assets
            if a.get("name", "").startswith("artcraft-launcher-") and a["name"].endswith(w)
        ),
        None,
    )
    if not pick:
        raise RuntimeError(
            f"No launcher build for this computer in the newest release. See {CRAFT_LAUNCHER}"
        )
    digest = pick.get("digest")
    if not digest:
        sums = next((a for a in assets if a.get("name") == "SHA256SUMS.txt"), None)
        if sums:
            try:
                txt = httpx.get(
                    sums["browser_download_url"], timeout=30, follow_redirects=True
                ).text
                for line in txt.splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1].lstrip("*") == pick["name"]:
                        digest = "sha256:" + parts[0].lower()
            except Exception:  # noqa: BLE001
                digest = None
    return {
        "name": pick["name"],
        "url": pick["browser_download_url"],
        "size": pick.get("size"),
        "digest": digest,
        "version": str(rel.get("tag_name", "")).lstrip("v"),
    }


# ---------------------------------------------------------------------------
# conversions
# ---------------------------------------------------------------------------

WRITER = {"doc", "docx", "odt", "rtf", "txt", "html", "htm"}
CALC = {"xls", "xlsx", "ods", "csv", "tsv"}
IMPRESS = {"ppt", "pptx", "odp"}
IMAGES = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff", "ico", "avif", "heic"}
AV = {
    "mp4",
    "mkv",
    "mov",
    "webm",
    "avi",
    "m4v",
    "mp3",
    "wav",
    "m4a",
    "aac",
    "flac",
    "ogg",
    "opus",
    "wma",
}
PANDOC_IN = {"md", "markdown", "html", "htm", "docx", "odt", "rst", "tex", "epub", "txt"}
PANDOC_OUT = {"md", "html", "docx", "odt", "rst", "tex", "epub", "txt"}
SCAD_OUT = {"stl", "3mf", "off", "amf", "dxf", "svg", "png"}
DATAS_OUT = {"docx", "xlsx", "pptx", "pdf", "html", "md", "txt"}


def routes(src_ext: str, to_ext: str) -> list[str]:
    """Which programs could convert ``src_ext`` → ``to_ext`` (ids, best first; "datas" = built in)."""
    s, t = src_ext.lower().lstrip("."), to_ext.lower().lstrip(".")
    out = []
    if s in ("md", "markdown", "txt") and t in DATAS_OUT:
        out.append("datas")
    if s in ("pdf", "docx", "xlsx", "pptx", "html", "htm") and t in ("txt", "md"):
        out.append("datas")
    office = WRITER | CALC | IMPRESS
    if s in office and (
        t == "pdf" or any(s in fam and t in fam for fam in (WRITER, CALC, IMPRESS))
    ):
        out.append("libreoffice")
    if s in PANDOC_IN and t in PANDOC_OUT:
        out.append("pandoc")
    if s == "svg" and t in ("png", "pdf", "eps", "emf"):
        out.append("inkscape")
    if s == "pdf" and t == "svg":
        out.append("inkscape")
    if s in IMAGES | {"svg"} and t in IMAGES | {"pdf"}:
        out.append("imagemagick")
    if s in AV and t in AV | {"gif"}:
        out.append("ffmpeg")
    if s == "scad" and t in SCAD_OUT:
        out.append("openscad")
    return out


def _run(cmd: list[str], timeout: int = 600, cwd: str | None = None) -> None:
    creation = {}
    if SYSTEM == "Windows":
        creation["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, **creation
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"{Path(cmd[0]).name} took longer than {timeout // 60} minutes and was stopped"
        ) from None
    if out.returncode != 0:
        raise RuntimeError(
            f"{Path(cmd[0]).name} failed: {(out.stderr or out.stdout or '').strip()[-400:]}"
        )


def convert(src: Path, to_ext: str, out_dir: Path | None = None, fetch_ffmpeg: bool = True) -> Path:
    """Convert ``src`` to ``to_ext`` next to it (or into ``out_dir``). Never overwrites: a
    number is added when the name is taken. Raises RuntimeError with a sentence the user can
    act on when nothing installed can do it."""
    src = Path(src)
    if not src.is_file():
        raise RuntimeError(f"{src.name} was not found")
    t = to_ext.lower().lstrip(".")
    s = src.suffix.lower().lstrip(".")
    if s == t:
        raise RuntimeError("the file already has that format")
    out_dir = Path(out_dir) if out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{src.stem}.{t}"
    n = 2
    while dest.exists():
        dest = out_dir / f"{src.stem} ({n}).{t}"
        n += 1
    possible = routes(s, t)
    missing = []
    for pid in possible:
        if pid == "datas":
            _datas_convert(src, dest, s, t)
            return dest
        exe = ffmpeg(fetch_ffmpeg) if pid == "ffmpeg" else find(pid)
        if not exe:
            missing.append(pid)
            continue
        if pid == "libreoffice":
            with tempfile.TemporaryDirectory(prefix="datas-lo-") as tmp:
                # its own profile folder, so a LibreOffice window that is open does not interfere
                profile = Path(tmp, "profile").as_uri()
                _run(
                    [
                        exe,
                        f"-env:UserInstallation={profile}",
                        "--headless",
                        "--convert-to",
                        t,
                        "--outdir",
                        tmp,
                        str(src),
                    ]
                )
                made = Path(tmp) / f"{src.stem}.{t}"
                if not made.exists():
                    raise RuntimeError(
                        "LibreOffice did not produce the file (format not supported for this document)"
                    )
                shutil.move(str(made), str(dest))
        elif pid == "pandoc":
            _run([exe, str(src), "-o", str(dest)])
        elif pid == "inkscape":
            _run([exe, str(src), f"--export-type={t}", f"--export-filename={dest}"])
        elif pid == "imagemagick":
            _run([exe, str(src), str(dest)])
        elif pid == "ffmpeg":
            _run(
                [exe, "-hide_banner", "-loglevel", "error", "-n", "-i", str(src), str(dest)],
                timeout=3600,
            )
        elif pid == "openscad":
            _run([exe, "-o", str(dest), str(src)], timeout=1800)
        if dest.exists():
            return dest
        raise RuntimeError("the program finished but the new file is not there")
    if missing:
        names = {p["id"]: p for p in PROGRAMS}
        hints = "; ".join(f"{names[m]['name']} ({names[m]['site']})" for m in missing if m in names)
        raise RuntimeError(
            f"Converting .{s} to .{t} needs a program that is not installed here: {hints}"
        )
    raise RuntimeError(f"Datas does not know a way to convert .{s} to .{t}")


def _datas_convert(src: Path, dest: Path, s: str, t: str) -> None:
    from datas import docs, export

    if s in ("md", "markdown", "txt"):
        export.render(src.read_text(encoding="utf-8", errors="replace"), t, dest, title=src.stem)
    else:
        dest.write_text(docs.extract_text(src.name, src.read_bytes()), encoding="utf-8")


# ---------------------------------------------------------------------------
# for the window
# ---------------------------------------------------------------------------


def listing(lang: str = "en") -> dict:
    from datas import mcp

    progs = []
    for p in detect():
        progs.append(
            {
                "id": p["id"],
                "name": p["name"],
                "group": p["group"],
                "site": p["site"],
                "does": p["does"].get(lang) or p["does"]["en"],
                "found": p["found"],
                "path": p.get("path"),
                "agent_tools": bool(p.get("agent_tools")),
                "verified": p.get("verified", True),
            }
        )
    servers = [
        {"name": k, "command": v["command"], "args": v["args"], "source": v.get("source", "yours")}
        for k, v in mcp.all_servers().items()
    ]
    return {
        "programs": progs,
        "connections": servers,
        "artcraft": {"site": CRAFT_SITE, "launcher": CRAFT_LAUNCHER},
        "ffmpeg": bool(ffmpeg()),
    }


def open_program(pid: str, file: str | None = None) -> None:
    """Start a program's window (optionally on a file)."""
    path = None
    for p in detect():
        if p["id"] == pid and p.get("found"):
            path = p["path"]
    if not path:
        raise RuntimeError("that program was not found on this computer")
    cmd = [path] + ([file] if file else [])
    if SYSTEM == "Darwin" and ".app/Contents/MacOS/" in path:
        app = path.split(".app/Contents/MacOS/")[0] + ".app"
        cmd = ["open", "-a", app] + ([file] if file else [])
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=SYSTEM != "Windows",
    )
