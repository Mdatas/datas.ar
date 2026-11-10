"""Fetch and manage prebuilt llama.cpp binaries.

We do not build an inference engine. llama.cpp (MIT, ggml-org) publishes prebuilt
archives for every platform on each release; we pick the right one for this device,
download it once, and pin the tag so every node in a pool runs the same RPC protocol.

Asset naming (from .github/workflows/release.yml in ggml-org/llama.cpp):

    llama-<tag>-bin-<platform>[-<backend>[-<version>]]-<arch>.(tar.gz|zip)
    cudart-llama-bin-win-cuda-<version>-<arch>.zip      (CUDA runtime DLLs, Windows)

    platform: ubuntu | macos | win | android | linux (snapdragon)
    backend : (none = CPU; Metal is built into macos) | vulkan | cuda-12.x | cuda-13.x |
              rocm-10.0 | sycl-fp16 | openvino-… | opencl-adreno
    arch    : x64 | arm64

Versioned releases (v0.7.0 …) carry no binaries; the rolling bNNNN builds do, so we walk
the release list until we find one with a matching asset.
"""

from __future__ import annotations

import io
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from datas.config import Config, runtime_dir
from datas.hardware.detect import DeviceSpec

REPO = "ggml-org/llama.cpp"
API_RELEASES = f"https://api.github.com/repos/{REPO}/releases"
ATOM_RELEASES = f"https://github.com/{REPO}/releases.atom"
DL_BASE = f"https://github.com/{REPO}/releases/download"

# The build this Datas release was tested against. Used when no tag is pinned yet and
# as the offline fallback when the GitHub API is unreachable. `datas runtime update`
# moves the pin to the newest build. All nodes of a pool must share one tag.
KNOWN_GOOD_TAG = "b11669"

# Version suffixes to probe when we cannot list a release's assets (API rate-limited or
# blocked). Newest first; the list only needs to contain versions that have shipped.
PROBE_VERSIONS = {
    "cuda": ["13.4", "12.8", "12.4", "13.3", "12.6"],
    "rocm": ["10.0", "7.1", "6.4"],
}

ProgressCB = Callable[[int, int | None], None]  # (bytes_done, bytes_total)


@dataclass
class AssetChoice:
    tag: str
    name: str
    url: str
    extra: list[tuple[str, str]]  # (name, url) companions, e.g. cudart pack
    # "sha256:<hex>" per file name, as published by GitHub with the release (when the API is
    # reachable); downloads are checked against it
    digests: dict[str, str] = field(default_factory=dict)


def _gh_headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "datas.ar"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def cuda_major_from_driver() -> int | None:
    """Read 'CUDA Version: 12.8' from nvidia-smi to pick a compatible CUDA build."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe], capture_output=True, text=True, timeout=8).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    m = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", out)
    return int(m.group(1)) if m else None


def backend_for(spec: DeviceSpec, override: str = "") -> str:
    if override:
        return override
    if spec.os == "darwin":
        return "metal"
    g = spec.best_gpu
    if not g:
        return "cpu"
    return g.backend  # cuda | rocm | vulkan | opencl | cpu


def asset_patterns(spec: DeviceSpec, backend: str) -> list[str]:
    """Ordered regex preferences for this device. First match in a release wins."""
    arch = "x64" if spec.arch == "x86_64" else "arm64"
    pats: list[str] = []
    if spec.os == "darwin":
        pats = [rf"llama-(b\d+)-bin-macos-{arch}\.tar\.gz"]
    elif spec.os == "android":
        qualcomm = any(g.vendor == "qualcomm" for g in spec.gpus)
        pats = [rf"llama-(b\d+)-bin-android-{arch}\.tar\.gz"]
        if qualcomm:  # Hexagon/Adreno-enabled build first, generic as fallback
            pats.insert(0, rf"llama-(b\d+)-bin-android-{arch}-snapdragon\.tar\.gz")
    elif spec.os == "windows":
        if backend == "cuda":
            major = cuda_major_from_driver() or 12
            pats.append(rf"llama-(b\d+)-bin-win-cuda-{major}\.\d+-{arch}\.zip")
            pats.append(rf"llama-(b\d+)-bin-win-cuda-12\.\d+-{arch}\.zip")
        if backend == "rocm":
            pats.append(rf"llama-(b\d+)-bin-win-rocm-[\d.]+-{arch}\.zip")
        if backend == "opencl":
            pats.append(rf"llama-(b\d+)-bin-win-opencl-adreno-{arch}\.zip")
        if backend in ("cuda", "rocm", "vulkan", "opencl"):
            pats.append(rf"llama-(b\d+)-bin-win-vulkan-{arch}\.zip")
        pats.append(rf"llama-(b\d+)-bin-win-cpu-{arch}\.zip")
    else:  # linux
        if backend == "cuda":
            major = cuda_major_from_driver() or 12
            pats.append(rf"llama-(b\d+)-bin-ubuntu-cuda-{major}\.\d+-{arch}\.tar\.gz")
            pats.append(rf"llama-(b\d+)-bin-ubuntu-cuda-12\.\d+-{arch}\.tar\.gz")
        if backend == "rocm":
            pats.append(rf"llama-(b\d+)-bin-ubuntu-rocm-[\d.]+-{arch}\.tar\.gz")
        if backend in ("cuda", "rocm", "vulkan", "opencl"):
            pats.append(rf"llama-(b\d+)-bin-ubuntu-vulkan-{arch}\.tar\.gz")
        pats.append(rf"llama-(b\d+)-bin-ubuntu-{arch}\.tar\.gz")
    return pats


def _match(assets: list[dict], pats: list[str]) -> dict | None:
    for p in pats:
        rx = re.compile(p)
        for a in assets:
            if rx.fullmatch(a["name"]):
                return a
    return None


def _companions(assets: list[dict], chosen: str) -> list[tuple[str, str]]:
    """CUDA builds need the matching cudart runtime pack (DLLs on Windows, .so on Linux)."""
    if "-cuda-" not in chosen:
        return []
    wants = {f"cudart-{chosen}"}  # linux: cudart-llama-bNNNN-bin-ubuntu-cuda-12.8-x64.tar.gz
    m = re.match(r"llama-(b\d+)-bin-(win-cuda-[\d.]+-\w+)\.zip", chosen)
    if m:
        wants.add(f"cudart-llama-bin-{m.group(2)}.zip")  # windows: no tag in the name
    return [(a["name"], a["browser_download_url"]) for a in assets if a["name"] in wants]


def latest_tag(client: httpx.Client | None = None) -> str | None:
    """Newest rolling build tag (bNNNN) via the API, else the Atom feed, else None."""
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True, headers=_gh_headers())
    try:
        try:
            r = client.get(API_RELEASES, params={"per_page": 20})
            if r.status_code == 200:
                for rel in r.json():
                    if re.fullmatch(r"b\d+", rel.get("tag_name", "")) and rel.get("assets"):
                        return rel["tag_name"]
        except httpx.HTTPError:
            pass
        try:
            r = client.get(ATOM_RELEASES)
            if r.status_code == 200:
                tags = re.findall(r"/releases/tag/(b\d+)", r.text)
                if tags:
                    return tags[0]
        except httpx.HTTPError:
            pass
        return None
    finally:
        if own:
            client.close()


def _probe_names(spec: DeviceSpec, backend: str, tag: str) -> list[str]:
    """Concrete asset names to try when we cannot list the release's assets."""
    names: list[str] = []
    for pat in asset_patterns(spec, backend):
        p = pat.replace(r"(b\d+)", tag)
        if r"\d+" in p or "[\\d.]+" in p:
            key = "cuda" if "cuda" in p else "rocm"
            for v in PROBE_VERSIONS[key]:
                concrete = re.sub(r"(cuda|rocm)-[^-]+-", rf"\1-{v}-", p)
                names.append(concrete.replace("\\.", "."))
        else:
            names.append(p.replace("\\.", "."))
    # de-dup, keep order
    seen: set[str] = set()
    return [n for n in names if not (n in seen or seen.add(n))]


def _exists(client: httpx.Client, url: str) -> bool:
    try:
        r = client.head(url, follow_redirects=False)
        return r.status_code in (200, 302, 301, 307)
    except httpx.HTTPError:
        return False


def resolve(
    spec: DeviceSpec, backend: str, tag: str = "", client: httpx.Client | None = None
) -> AssetChoice:
    """Find the release + asset for this device.

    Order: (1) GitHub API listing for the pinned/known tag, (2) HEAD-probe constructed
    asset URLs for that tag (works when the API is rate-limited or blocked).
    """
    tag = tag or KNOWN_GOOD_TAG
    pats = asset_patterns(spec, backend)
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True, headers=_gh_headers())
    try:
        try:
            r = client.get(f"{API_RELEASES}/tags/{tag}")
            if r.status_code == 200:
                assets = r.json().get("assets", [])
                a = _match(assets, pats)
                if a:
                    return AssetChoice(
                        tag,
                        a["name"],
                        a["browser_download_url"],
                        _companions(assets, a["name"]),
                        {x["name"]: x["digest"] for x in assets if x.get("digest")},
                    )
                raise RuntimeError(f"Release {tag} has no asset matching {pats}")
        except httpx.HTTPError:
            pass
        # Fallback: probe
        for name in _probe_names(spec, backend, tag):
            url = f"{DL_BASE}/{tag}/{name}"
            if _exists(client, url):
                extra: list[tuple[str, str]] = []
                if "-cuda-" in name:
                    for cand in (
                        f"cudart-{name}",
                        re.sub(r"^llama-b\d+-bin-", "cudart-llama-bin-", name),
                    ):
                        curl = f"{DL_BASE}/{tag}/{cand}"
                        if _exists(client, curl):
                            extra.append((cand, curl))
                            break
                return AssetChoice(tag, name, url, extra)
        raise RuntimeError(
            f"Could not find a llama.cpp {tag} build for {spec.os}/{spec.arch}/{backend}. "
            f"Check https://github.com/{REPO}/releases/tag/{tag} or pin another tag "
            f"with `datas runtime pin <tag>`."
        )
    finally:
        if own:
            client.close()


def _download(
    url: str,
    dest: Path,
    client: httpx.Client,
    progress: ProgressCB | None = None,
    digest: str | None = None,
) -> Path:
    """``digest`` ("sha256:<hex>"): the file is deleted and an error raised when it differs."""
    import hashlib

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    with client.stream("GET", url) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) or None
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if total and tmp.stat().st_size != total:
        tmp.unlink(missing_ok=True)
        raise OSError(f"Incomplete download of {dest.name}; try again.")
    if digest and digest.startswith("sha256:") and digest[7:].lower() != h.hexdigest():
        tmp.unlink(missing_ok=True)
        raise ValueError(
            f"{dest.name} does not match the checksum published with the release; it was deleted."
        )
    tmp.replace(dest)
    return dest


def _extract(archive: Path, into: Path) -> None:
    into.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
    else:
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(into, filter="data") if hasattr(tarfile, "data_filter") else t.extractall(
                into
            )


BINARIES = (
    "llama-server",
    "rpc-server",
    "ggml-rpc-server",
    "llama-bench",
    "llama-cli",
    "llama-completion",
)
# the RPC worker was renamed upstream; accept both spellings
ALIASES = {"rpc-server": ("ggml-rpc-server", "rpc-server")}


def find_binary(root: Path, name: str) -> Path | None:
    ext = ".exe" if platform.system() == "Windows" else ""
    for candidate in ALIASES.get(name, (name,)):
        for p in root.rglob(candidate + ext):
            if p.is_file():
                return p
    return None


def install(
    spec: DeviceSpec,
    cfg: Config,
    progress: ProgressCB | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    """Ensure a llama.cpp build is installed for this device; return its directory."""
    backend = backend_for(spec, cfg.backend)
    with httpx.Client(timeout=120, follow_redirects=True, headers=_gh_headers()) as client:
        choice = resolve(spec, backend, cfg.llamacpp_tag, client)
        dest_dir = runtime_dir() / choice.tag
        marker = dest_dir / ".datas-ok"
        if marker.exists() and find_binary(dest_dir, "llama-server"):
            log(f"llama.cpp {choice.tag} already installed ({dest_dir})")
            return dest_dir
        log(f"Downloading llama.cpp {choice.tag}: {choice.name}")
        archive = _download(
            choice.url,
            runtime_dir() / "downloads" / choice.name,
            client,
            progress,
            choice.digests.get(choice.name),
        )
        if choice.digests.get(choice.name):
            log("Checksum matches the one published with the release.")
        _extract(archive, dest_dir)
        archive.unlink(missing_ok=True)  # the archive is not needed once unpacked
        for name, url in choice.extra:
            log(f"Downloading companion: {name}")
            comp = _download(
                url, runtime_dir() / "downloads" / name, client, progress, choice.digests.get(name)
            )
            # cudart DLLs must sit next to llama-server.exe
            server = find_binary(dest_dir, "llama-server")
            _extract(comp, server.parent if server else dest_dir)
        # make binaries executable on POSIX
        if platform.system() != "Windows":
            for b in BINARIES:
                p = find_binary(dest_dir, b)
                if p:
                    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            if spec.os == "darwin":  # strip Gatekeeper quarantine on the extracted tree
                subprocess.run(
                    ["xattr", "-dr", "com.apple.quarantine", str(dest_dir)], capture_output=True
                )
        marker.write_text(f"{choice.tag}\n{choice.name}\n{backend}\n")
        cfg.llamacpp_tag = choice.tag
        cfg.save()
        log(f"Installed llama.cpp {choice.tag} ({backend}) → {dest_dir}")
        return dest_dir


def installed_dir(cfg: Config) -> Path | None:
    if cfg.llamacpp_tag:
        d = runtime_dir() / cfg.llamacpp_tag
        if find_binary(d, "llama-server"):
            return d
    # any installed build
    for d in sorted(runtime_dir().glob("b*"), reverse=True):
        if find_binary(d, "llama-server"):
            return d
    return None


def binary(cfg: Config, name: str = "llama-server") -> Path:
    d = installed_dir(cfg)
    if not d:
        raise FileNotFoundError("llama.cpp is not installed yet — run `datas install` first.")
    p = find_binary(d, name)
    if not p:
        raise FileNotFoundError(
            f"{name} not found in {d}. This build may not include it; see docs/RUNTIME.md."
        )
    return p


def version_string(cfg: Config) -> str:
    try:
        out = subprocess.run(
            [str(binary(cfg)), "--version"], capture_output=True, text=True, timeout=10
        )
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as e:  # pragma: no cover
        return f"unknown ({e})"


def self_test_extract(data: bytes, suffix: str) -> list[str]:
    """Used by tests: list members of an in-memory archive the way we extract them."""
    if suffix == ".zip":
        return zipfile.ZipFile(io.BytesIO(data)).namelist()
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz").getnames()
