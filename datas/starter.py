"""The small starter AI that ships inside the Datas installers (Qwen3 0.6B, Q4_0, about 0.4 GB):
something to ask from the very first minute — about AI, about Datas, about everything in its
guides — with no download, on a Raspberry Pi or an old computer as well.

The build (``scripts/fetch_starter.py``) puts the file, checked against its SHA-256, into
``datas/starter/``; on start Datas places it among the AIs (a hard link when the disk allows,
so it takes no extra space, else a copy) and, when no other AI is there yet, starts it.
A plain ``pip install`` has no starter inside: it is then fetched like any AI.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ID, QUANT = "qwen3-0.6b", "Q4_0"


def bundled_file() -> Path | None:
    d = Path(__file__).resolve().parent / "starter"
    files = sorted(d.glob("*.gguf")) if d.is_dir() else []
    return files[0] if files else None


def install_bundled(catalog=None) -> Path | None:  # noqa: ANN001
    """Place the shipped starter among the AIs, once. Returns where it is, or None."""
    src = bundled_file()
    if not src:
        return None
    from datas import catalog as C
    from datas.runtime.downloader import local_path

    cat = catalog or C.load()
    m = cat.get(ID)
    f = m.file(QUANT)
    dest = local_path(m, f)
    if src.name != f.path or src.stat().st_size != f.bytes:
        return None  # not the file the catalog describes: leave it
    if dest.exists() and dest.stat().st_size == f.bytes:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    part.unlink(missing_ok=True)
    try:
        os.link(src, part)  # same disk: no second copy of 0.4 GB
    except OSError:
        shutil.copyfile(src, part)
    part.replace(dest)
    return dest
