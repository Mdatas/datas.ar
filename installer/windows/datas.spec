# PyInstaller spec — builds a self-contained Datas folder (no Python required on the target).
#   pyinstaller installer/windows/datas.spec
# Used by .github/workflows/windows-installer.yml; the result feeds datas.iss (Inno Setup).
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), "..", ".."))

datas = [
    (os.path.join(ROOT, "datas", "catalog", "models.json"), os.path.join("datas", "catalog")),
    (os.path.join(ROOT, "datas", "server", "ui", "index.html"), os.path.join("datas", "server", "ui")),
]
binaries = []
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("datas")
    + ["cpuinfo", "zeroconf", "gguf", "huggingface_hub", "platformdirs", "psutil", "numpy", "pydantic", "pydantic_core"]
)
for pkg in ("gguf", "zeroconf", "huggingface_hub", "rich", "typer", "fastapi", "starlette"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

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
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="datas",
    icon=os.path.join(ROOT, "installer", "windows", "datas.ico"),
    console=True,
    disable_windowed_traceback=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Datas")
