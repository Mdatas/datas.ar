# PyInstaller spec — one folder, two executables:
#   Datas.exe     windowed: opens the Datas window (what the Desktop icon launches)
#   datas-cli.exe console:  the full command line for advanced users
#   pyinstaller --noconfirm installer/windows/datas.spec
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), "..", ".."))
ICON = os.path.join(ROOT, "installer", "windows", "datas.ico")

datas = [
    (os.path.join(ROOT, "datas", "catalog", "models.json"), os.path.join("datas", "catalog")),
    (os.path.join(ROOT, "datas", "sources.json"), "datas"),
    (os.path.join(ROOT, "datas", "server", "ui", "index.html"), os.path.join("datas", "server", "ui")),
    (os.path.join(ROOT, "datas", "server", "ui", "agent.html"), os.path.join("datas", "server", "ui")),
    (os.path.join(ROOT, "datas", "server", "ui", "datas.ico"), os.path.join("datas", "server", "ui")),
    (os.path.join(ROOT, "datas", "server", "ui", "datas.png"), os.path.join("datas", "server", "ui")),
    (ICON, "."),
]
binaries = []
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("datas")
    + ["cpuinfo", "zeroconf", "gguf", "huggingface_hub", "platformdirs", "psutil", "numpy", "pydantic", "pydantic_core",
       "webview", "clr_loader", "pythonnet"]
)
for pkg in ("gguf", "zeroconf", "huggingface_hub", "rich", "typer", "fastapi", "starlette", "webview"):
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
