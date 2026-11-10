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
    (os.path.join(ROOT, "datas", "assistants", "catalog.json"), os.path.join("datas", "assistants")),
    (os.path.join(ROOT, "datas", "learn", "catalog.json"), os.path.join("datas", "learn")),
    (os.path.join(ROOT, "datas", "learn", "lessons.en.md"), os.path.join("datas", "learn")),
    (os.path.join(ROOT, "datas", "learn", "lessons.es.md"), os.path.join("datas", "learn")),
    # whole folders: the window (pages, style, scripts, fonts, icons) and the fonts used in PDFs
    (os.path.join(ROOT, "datas", "server", "ui"), os.path.join("datas", "server", "ui")),
    (os.path.join(ROOT, "datas", "fonts"), os.path.join("datas", "fonts")),
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
# document formats: python-docx and python-pptx ship template files that must travel with them
for pkg in ("gguf", "zeroconf", "huggingface_hub", "rich", "typer", "fastapi", "starlette", "webview",
            "docx", "pptx", "openpyxl", "fpdf", "pypdf", "markdown_it", "cryptography",
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

# macOS signing: set DATAS_MACOS_IDENTITY to a "Developer ID Application: …" identity that is
# in the keychain and every binary is signed with it for notarization (docs/SIGNING.md).
# Without it PyInstaller signs "ad hoc", which is what an unsigned download is.
MAC_ID = (os.environ.get("DATAS_MACOS_IDENTITY") or None) if MAC else None
ENTITLEMENTS = os.path.join(ROOT, "installer", "macos", "entitlements.plist") if MAC_ID else None

exe_gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Datas",
    icon=ICON,
    console=False,          # no terminal window — the app opens its own window
    disable_windowed_traceback=False,
    upx=False,
    codesign_identity=MAC_ID,
    entitlements_file=ENTITLEMENTS,
)
exe_cli = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="datas-cli",
    icon=ICON,
    console=True,
    upx=False,
    codesign_identity=MAC_ID,
    entitlements_file=ENTITLEMENTS,
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
            # macOS closes an app that uses these without saying why
            "NSMicrophoneUsageDescription": "Datas listens only while you use the microphone button, to turn your voice into text on this Mac. Nothing is sent anywhere.",
            "NSCameraUsageDescription": "Datas takes a picture only when you ask for one, to show it to the AI on this Mac. Nothing is sent anywhere.",
            "NSLocalNetworkUsageDescription": "Datas finds and talks to the devices you linked yourself on this network.",
            "NSBonjourServices": ["_datas-link._tcp"],
            "NSAppleEventsUsageDescription": "Datas controls other programs only when you allow the agent to.",
        },
        codesign_identity=MAC_ID,
        entitlements_file=ENTITLEMENTS,
    )
