# PyInstaller spec for every desktop OS — one folder (or .app), two executables:
#   Datas      windowed: opens the Datas window (what the Desktop icon launches)
#   datas-cli  console:  the full command line for advanced users
#   pyinstaller --noconfirm installer/datas.spec
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))
WIN, MAC, LINUX = sys.platform == "win32", sys.platform == "darwin", sys.platform.startswith("linux")
ICON = os.path.join(ROOT, "installer", "windows", "datas.ico") if WIN else (
    os.path.join(ROOT, "installer", "macos", "datas.icns") if MAC else os.path.join(ROOT, "installer", "windows", "datas-256.png"))
if not os.path.exists(ICON):
    ICON = None

datas = [
    (os.path.join(ROOT, "datas", "catalog", "models.json"), os.path.join("datas", "catalog")),
    (os.path.join(ROOT, "datas", "catalog", "media.json"), os.path.join("datas", "catalog")),
    (os.path.join(ROOT, "datas", "sources.json"), "datas"),
    (os.path.join(ROOT, "datas", "apps", "apps.json"), os.path.join("datas", "apps")),
    (os.path.join(ROOT, "datas", "server", "ui", "index.html"), os.path.join("datas", "server", "ui")),
    (os.path.join(ROOT, "datas", "server", "ui", "agent.html"), os.path.join("datas", "server", "ui")),
    (os.path.join(ROOT, "datas", "server", "ui", "datas.ico"), os.path.join("datas", "server", "ui")),
    (os.path.join(ROOT, "datas", "server", "ui", "datas.png"), os.path.join("datas", "server", "ui")),
]
if ICON:
    datas.append((ICON, "."))
binaries = []
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("datas")
    + ["cpuinfo", "zeroconf", "gguf", "huggingface_hub", "platformdirs", "psutil", "numpy", "pydantic", "pydantic_core", "webview"]
)
if WIN:
    hiddenimports += ["clr_loader", "pythonnet"]
if LINUX:  # Qt backend for pywebview: self-contained, works on Debian and Arch families alike
    hiddenimports += ["qtpy", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore", "PyQt6.QtWebChannel",
                      "PyQt6.QtNetwork", "PyQt6.QtPrintSupport", "PyQt6.QtOpenGLWidgets"]
# voice stack (optional at runtime; bundled when installed): whisper.cpp bindings, Kokoro + ONNX Runtime,
# espeak-ng data for phonemes, PortAudio for the microphone
for pkg in ("gguf", "zeroconf", "huggingface_hub", "rich", "typer", "fastapi", "starlette", "webview",
            "pywhispercpp", "kokoro_onnx", "onnxruntime", "espeakng_loader", "phonemizer", "sounddevice", "_sounddevice_data"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [os.path.join(ROOT, "datas", "__main__.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Datas",
    icon=ICON,
    console=False,          # no terminal window — the app opens its own window
    disable_windowed_traceback=False,
    upx=False,
)
exe_cli = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="datas-cli",
    icon=ICON,
    console=True,
    upx=False,
)
coll = COLLECT(exe_gui, exe_cli, a.binaries, a.datas, strip=False, upx=False, name="Datas")

if MAC:
    app = BUNDLE(
        coll,
        name="Datas.app",
        icon=ICON,
        bundle_identifier="ar.datas.app",
        info_plist={
            "CFBundleName": "Datas",
            "CFBundleDisplayName": "Datas.ar",
            "CFBundleShortVersionString": os.environ.get("DATAS_VERSION", "0.0.0"),
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "GPL-3.0-or-later — https://github.com/Mdatas/datas.ar",
        },
    )
