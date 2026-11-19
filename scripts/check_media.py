#!/usr/bin/env python3
"""Check every file of the picture and video recipes (datas/catalog/media.json) the way Datas
will download it: without a Hugging Face account. A gated file (one that asks for a sign-in,
"401 Unauthorized") fails here instead of on someone's computer.

    python scripts/check_media.py            # check; exit 1 if a file cannot be downloaded
    python scripts/check_media.py --write    # also store each file's size and SHA-256
    python scripts/check_media.py --find ae.safetensors 335304388 REPO [REPO …]
                                             # look for an ungated, identical copy of a file

The SHA-256 is the one Hugging Face publishes for the file (its "LFS object id"); a copy in
another repository with the same SHA-256 is the same file, byte for byte.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "datas" / "catalog" / "media.json"
HF = "https://huggingface.co"
client = httpx.Client(timeout=60, follow_redirects=False, headers={"User-Agent": "datas-check"})


def tree(repo: str) -> dict[str, dict]:
    """path -> {size, sha256} for every file of the repository (public metadata)."""
    out: dict[str, dict] = {}
    r = client.get(f"{HF}/api/models/{repo}/tree/main", params={"recursive": "true"})
    r.raise_for_status()
    for e in r.json():
        if e.get("type") == "file":
            lfs = e.get("lfs") or {}
            out[e["path"]] = {"size": lfs.get("size") or e.get("size"), "sha256": lfs.get("oid")}
    return out


def gated(repo: str) -> str | bool:
    r = client.get(f"{HF}/api/models/{repo}")
    r.raise_for_status()
    return r.json().get("gated", False)


def downloadable(repo: str, path: str) -> tuple[bool, str]:
    """Without any account: does the download start? (only the first byte is asked for)"""
    url = f"{HF}/{repo}/resolve/main/{path}"
    r = client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True)
    return r.status_code in (200, 206), f"HTTP {r.status_code}"


def media_files(d: dict):
    for kind in ("image", "video"):
        for rid, recipe in d.get(kind, {}).get("recipes", {}).items():
            for part, spec in recipe.items():
                if isinstance(spec, dict) and spec.get("repo") and spec.get("files"):
                    yield kind, rid, part, spec


def check(write: bool) -> int:
    d = json.loads(MEDIA.read_text())
    bad = 0
    trees: dict[str, dict] = {}
    for kind, rid, part, spec in media_files(d):
        repo = spec["repo"]
        g = gated(repo)
        trees.setdefault(repo, tree(repo))
        for f in spec["files"]:
            meta = trees[repo].get(f["file"]) or {}
            ok, why = downloadable(repo, f["file"])
            print(f"{'ok  ' if ok else 'FAIL'} {kind}/{rid}/{part}: {repo}/{f['file']} "
                  f"gated={g} {why} size={meta.get('size')} sha256={meta.get('sha256')}")
            bad += not ok
            if write and meta.get("sha256"):
                f["sha256"] = meta["sha256"]
                if meta.get("size"):
                    f["bytes"] = meta["size"]
    if write:
        MEDIA.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print(f"{bad} file(s) cannot be downloaded without an account")
    return 1 if bad else 0


def find(name: str, size: int, repos: list[str]) -> None:
    want = None
    for repo in repos:
        try:
            files = tree(repo)
            g = gated(repo)
        except httpx.HTTPError as e:
            print(f"{repo}: {e}")
            continue
        for path, meta in files.items():
            if path.endswith(name) or meta.get("size") == size:
                ok, why = downloadable(repo, path)
                print(f"{repo}/{path} gated={g} downloadable={ok} ({why}) "
                      f"size={meta.get('size')} sha256={meta.get('sha256')}")
                if want is None and g:
                    want = meta.get("sha256")
    print(f"the gated original's sha256: {want}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--find":
        find(sys.argv[2], int(sys.argv[3]), sys.argv[4:])
    else:
        sys.exit(check("--write" in sys.argv))
