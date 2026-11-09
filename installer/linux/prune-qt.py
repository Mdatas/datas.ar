#!/usr/bin/env python3
"""Shrink the Linux PyInstaller bundle: keep only the Qt libraries the app actually links to.

PyInstaller's Qt hooks copy every library in Qt6/lib that *any* collected module could reach
(Quick3D, ShaderTools, QuickControls, ...). We only use QtWebEngineWidgets, so walk the ELF
NEEDED graph from the Python extension modules + plugins and delete everything unreachable,
plus translations (keeping the WebEngine locales), the qml tree and stray .debug files.
    installer/linux/prune-qt.py dist/Datas
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

bundle = Path(sys.argv[1]).resolve()
qt = bundle / "_internal" / "PyQt6"
lib = qt / "Qt6" / "lib"
if not lib.is_dir():
    print("no PyQt6 in bundle, nothing to prune")
    sys.exit(0)


def needed(path: Path) -> set[str]:
    out = subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True).stdout
    return set(re.findall(r"\[(libQt6[^\]]+|libicu[^\]]+)\]", out))


roots = list(qt.glob("*.so")) + [p for p in (qt / "Qt6" / "plugins").rglob("*.so")]
keep: set[str] = set()
todo = [p for p in roots]
while todo:
    p = todo.pop()
    for name in needed(p):
        if name in keep:
            continue
        keep.add(name)
        cand = lib / name
        if cand.exists():
            todo.append(cand)

before = sum(f.stat().st_size for f in bundle.rglob("*") if f.is_file())
removed = 0
for f in lib.iterdir():
    base = f.name
    # libQt6Foo.so.6.7.1 / libQt6Foo.so.6 / libicudata.so.73 ...
    key = re.sub(r"(\.so\.\d+)\..*$", r"\1", base)
    if (base.startswith("libQt6") or base.startswith("libicu")) and key not in keep and base not in keep:
        removed += f.stat().st_size
        f.unlink()
for d in ("qml", "libexec/qmlls", "resources/qtwebengine_devtools_resources.pak"):
    p = qt / "Qt6" / d
    if p.is_dir():
        removed += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        shutil.rmtree(p)
    elif p.is_file():
        removed += p.stat().st_size
        p.unlink()
tr = qt / "Qt6" / "translations"
if tr.is_dir():
    for f in tr.iterdir():
        if f.is_file():  # .qm files for Qt's own dialogs
            removed += f.stat().st_size
            f.unlink()
    loc = tr / "qtwebengine_locales"
    if loc.is_dir():  # Chromium UI strings (context menus): keep the languages Datas speaks + neighbours
        for f in loc.iterdir():
            if f.stem not in {"en-US", "en-GB", "es", "es-419", "pt-BR", "pt-PT", "it", "fr", "de"}:
                removed += f.stat().st_size
                f.unlink()
for f in bundle.rglob("*.debug"):
    removed += f.stat().st_size
    f.unlink()
after = before - removed
print(f"pruned {removed/1e6:.0f} MB: {before/1e6:.0f} MB -> {after/1e6:.0f} MB; kept Qt libs: {sorted(keep)}")
