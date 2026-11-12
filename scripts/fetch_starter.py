#!/usr/bin/env python3
"""Put the starter AI (Qwen3 0.6B Q4_0) into datas/starter/ for the installers to ship.
Downloaded from Hugging Face and checked against the SHA-256 pinned in the catalog (else the
one Hugging Face publishes). Used by the build workflows before PyInstaller and the APK."""

import sys
from pathlib import Path

from datas import catalog as C
from datas.runtime.downloader import download_file
from datas.starter import ID, QUANT

out = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(__file__).resolve().parent.parent / "datas" / "starter"
)
m = C.load().get(ID)
f = m.file(QUANT)
dest = download_file(m.hf_repo, f.path, out / f.path, f.bytes, pinned_sha256=f.sha256)
print(f"starter AI ready: {dest} ({dest.stat().st_size} bytes)")
