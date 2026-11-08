"""Model downloads from Hugging Face with resume, progress and SHA-256 verification.

Reuses ``huggingface_hub`` for URL resolution, auth (HF_TOKEN for gated repos) and file
metadata (the LFS sha256 the Hub publishes for every large file). The transfer itself is
a plain HTTP range download so the UI can show progress and resume after a dropped
connection. Verification is against the Hub's own hash — a corrupted or tampered file is
deleted, never loaded.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from huggingface_hub import HfApi, hf_hub_url

from datas.catalog import CatalogModel, ModelFile
from datas.config import models_dir

ProgressCB = Callable[[int, int | None], None]


@dataclass
class RemoteFile:
    url: str
    size: int | None
    sha256: str | None


def _headers() -> dict[str, str]:
    h = {"User-Agent": "datas.ar"}
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def remote_info(repo: str, path: str) -> RemoteFile:
    """Size and sha256 as published by the Hub (no download)."""
    api = HfApi()
    info = api.get_paths_info(repo, [path], repo_type="model")
    size = sha = None
    for e in info:
        if getattr(e, "path", None) == path:
            size = getattr(e, "size", None)
            lfs = getattr(e, "lfs", None)
            sha = getattr(lfs, "sha256", None) if lfs else None
    return RemoteFile(hf_hub_url(repo, path), size, sha)


def local_path(model: CatalogModel, f: ModelFile | str) -> Path:
    name = f.path if isinstance(f, ModelFile) else f
    return models_dir() / model.id / name


def is_downloaded(model: CatalogModel, f: ModelFile) -> bool:
    p = local_path(model, f)
    return p.exists() and p.stat().st_size == f.bytes


def sha256_of(path: Path, progress: ProgressCB | None = None) -> str:
    h = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return h.hexdigest()


def download_file(
    repo: str,
    path: str,
    dest: Path,
    expected_size: int | None = None,
    progress: ProgressCB | None = None,
    verify: bool = True,
    log: Callable[[str], None] = print,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        meta = remote_info(repo, path)
    except Exception as e:  # offline metadata is not fatal; we can still try the download
        log(f"Could not read Hub metadata ({e}); continuing without hash verification.")
        meta = RemoteFile(hf_hub_url(repo, path), expected_size, None)
    total = meta.size or expected_size
    if dest.exists() and total and dest.stat().st_size == total:
        log(f"Already downloaded: {dest.name}")
        return dest
    done = part.stat().st_size if part.exists() else 0
    headers = _headers()
    if done:
        headers["Range"] = f"bytes={done}-"
        log(f"Resuming {dest.name} at {done / 2**20:.0f} MiB")
    with httpx.Client(
        timeout=httpx.Timeout(60, read=300), follow_redirects=True, headers=headers
    ) as client:
        with client.stream("GET", meta.url) as r:
            if r.status_code == 416:  # already complete
                pass
            else:
                r.raise_for_status()
                if done and r.status_code != 206:
                    done = 0  # server ignored Range: start over
                    mode = "wb"
                else:
                    mode = "ab" if done else "wb"
                if total is None:
                    cl = r.headers.get("Content-Length")
                    total = (int(cl) + done) if cl else None
                with part.open(mode) as fh:
                    for chunk in r.iter_bytes(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
    if total and part.stat().st_size != total:
        raise OSError(f"Incomplete download: {part.stat().st_size} of {total} bytes")
    if verify and meta.sha256:
        log("Verifying SHA-256 …")
        got = sha256_of(part)
        if got != meta.sha256:
            part.unlink(missing_ok=True)
            raise ValueError(
                f"SHA-256 mismatch for {path}: expected {meta.sha256}, got {got}. File deleted."
            )
    part.replace(dest)
    return dest


def download_model(
    model: CatalogModel,
    f: ModelFile,
    progress: ProgressCB | None = None,
    with_vision: bool = False,
    log: Callable[[str], None] = print,
) -> Path:
    dest = local_path(model, f)
    out = download_file(model.hf_repo, f.path, dest, f.bytes, progress, log=log)
    if with_vision and "mmproj" in model.extras:
        mp = model.extras["mmproj"]
        download_file(
            model.hf_repo, mp.path, local_path(model, mp.path), mp.bytes, progress, log=log
        )
    return out


def installed_models() -> list[dict]:
    """Every GGUF on disk under the models dir (catalog or user-provided)."""
    out: list[dict] = []
    for p in sorted(models_dir().rglob("*.gguf")):
        if p.name.startswith(("mmproj-", "mtp-", "dflash-", "dspark-", "eagle3-")):
            continue
        out.append(
            {
                "model_id": p.parent.name if p.parent != models_dir() else "custom",
                "file": p.name,
                "path": str(p),
                "bytes": p.stat().st_size,
            }
        )
    return out
