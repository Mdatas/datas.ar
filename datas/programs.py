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
import shutil
import subprocess
import tempfile
from pathlib import Path

from datas.config import home

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
    """Path of an installed program by id (``ffmpeg`` falls back to a bundled download)."""
    for p in detect():
        if p["id"] == pid and p.get("found"):
            return p.get("cli") if p.get("group") == "artcraft" and p.get("cli") else p["path"]
    return None


def ffmpeg(fetch: bool = False) -> str | None:
    """The system's FFmpeg, else (with ``fetch``) a static build downloaded once into the
    Datas folder by the ``static-ffmpeg`` package."""
    exe = find("ffmpeg")
    if exe or not fetch:
        return exe
    try:
        from static_ffmpeg import run

        ff, _probe = run.get_or_fetch_platform_executables_else_raise()
        return ff
    except Exception:  # noqa: BLE001 - package missing or no connection
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
