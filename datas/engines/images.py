"""Making images with stable-diffusion.cpp (leejet, MIT) — the same download-and-run pattern as
llama.cpp: a pinned prebuilt release, a recipe of model files from Hugging Face with exact sizes,
an ``sd-server`` subprocess with an HTTP API, and nothing kept on disk in Forget mode.

Recipe today: **Z-Image-Turbo** (Tongyi-MAI, 6 B parameters, 8 steps, no CFG) — the smallest model
that makes good 1024-px pictures and runs on a 4 GB graphics card with weights streamed from RAM
(``--offload-to-cpu``), or on the processor alone (slow: minutes per image). Files: the diffusion
model in GGUF (quantisation chosen by memory), the Qwen3-4B text encoder in GGUF, and the FLUX
autoencoder (VAE). Verified sizes live in ``datas/catalog/media.json``.
"""

from __future__ import annotations

import base64
import json
import os
import re
import signal
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from datas.config import Config, home, logs_dir
from datas.hardware.detect import DeviceSpec
from datas.runtime import downloader

if TYPE_CHECKING:
    from datas.orchestrator import Job

GiB = 2**30
REPO = "leejet/stable-diffusion.cpp"
# Pinned release: assets verified 2026-11-09 (9 binaries + cudart). Newer tags follow the same naming.
KNOWN_GOOD_TAG = "master-920-2f88688"
API_RELEASE = f"https://api.github.com/repos/{REPO}/releases/tags/{{tag}}"
DOWNLOAD = f"https://github.com/{REPO}/releases/download/{{tag}}/{{asset}}"


def media() -> dict:
    with resources.files("datas.catalog").joinpath("media.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def recipe_of(choice: ImageChoice) -> dict:
    return media()[choice.kind]["recipes"][choice.recipe]


def catalog() -> dict:
    with resources.files("datas.catalog").joinpath("media.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)["image"]


def sd_dir() -> Path:
    d = home() / "sdcpp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def images_dir() -> Path:
    d = home() / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = home() / "models" / "image"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# which engine build


def backend_for(spec: DeviceSpec, cfg: Config | None = None) -> str:
    """cpu | vulkan | cuda | rocm | metal. Vulkan is the default on every GPU (small download,
    works with the normal driver); CUDA/ROCm only when the user asks (Settings → Advanced)."""
    forced = getattr(cfg, "image_backend", "auto") if cfg else "auto"
    if forced and forced != "auto":
        return forced
    if spec.os == "darwin":
        return "metal"
    if spec.gpus and not all(g.vendor == "unknown" for g in spec.gpus):
        return "vulkan"
    return "cpu"


def asset_pattern(spec: DeviceSpec, backend: str) -> str:
    """Regex matching the release asset for this OS/backend (names verified against the release)."""
    sha = r"[0-9a-f]{7}"
    if spec.os == "windows":
        b = {"cpu": "cpu", "vulkan": "vulkan", "cuda": "cuda12", "rocm": r"rocm-[\d.]+"}[backend]
        return rf"^sd-master-{sha}-bin-win-{b}-x64\.zip$"
    if spec.os == "darwin":
        return rf"^sd-master-{sha}-bin-Darwin-macOS-[\d.]+-arm64\.zip$"
    b = {"cpu": "", "vulkan": "-vulkan", "cuda": "-cuda", "rocm": r"-rocm-[\d.]+"}[backend]
    return rf"^sd-master-{sha}-bin-Linux-Ubuntu-[\d.]+-x86_64{b}\.zip$"


def _release_assets(tag: str) -> list[dict]:
    r = httpx.get(
        API_RELEASE.format(tag=tag),
        timeout=30,
        headers={"User-Agent": "datas.ar", "Accept": "application/vnd.github+json"},
        follow_redirects=True,
    )
    r.raise_for_status()
    return [
        {"name": a["name"], "url": a["browser_download_url"], "size": a["size"]}
        for a in r.json().get("assets", [])
    ]


def _guess_assets(tag: str) -> list[dict]:
    """Offline fallback when the GitHub API is unreachable: the deterministic names."""
    sha = tag.rsplit("-", 1)[-1]
    names = [
        f"sd-master-{sha}-bin-win-cpu-x64.zip",
        f"sd-master-{sha}-bin-win-vulkan-x64.zip",
        f"sd-master-{sha}-bin-win-cuda12-x64.zip",
        f"sd-master-{sha}-bin-Linux-Ubuntu-24.04-x86_64.zip",
        f"sd-master-{sha}-bin-Linux-Ubuntu-24.04-x86_64-vulkan.zip",
    ]
    return [{"name": n, "url": DOWNLOAD.format(tag=tag, asset=n), "size": None} for n in names]


_ACTIVE_TAG = ""  # "" = the build this version of Datas was tested with


def set_tag(tag: str) -> None:
    """Choose which installed build is used (Settings → Updates). Empty = the tested one."""
    global _ACTIVE_TAG
    _ACTIVE_TAG = tag or ""


def active_tag() -> str:
    return _ACTIVE_TAG or KNOWN_GOOD_TAG


def installed_dir(tag: str | None = None) -> Path | None:
    d = sd_dir() / (tag or active_tag())
    return d if d.exists() and binary(d) else None


def binary(d: Path) -> Path | None:
    for cand in d.rglob("sd-server*"):
        if cand.is_file() and cand.suffix in ("", ".exe"):
            return cand
    return None


def ensure_runtime(
    spec: DeviceSpec, cfg: Config, job: Job | None = None, tag: str | None = None
) -> Path:
    say = job.say if job else print
    tag = tag or active_tag()
    d = sd_dir() / tag
    exe = binary(d) if d.exists() else None
    if exe:
        say(f"Image engine already installed: {exe.name} ({tag})")
        return exe
    backend = backend_for(spec, cfg)
    pat = re.compile(asset_pattern(spec, backend))
    try:
        assets = _release_assets(tag)
    except Exception as e:  # noqa: BLE001 - API blocked/offline → deterministic names
        say(f"GitHub API unavailable ({e}); using known file names")
        assets = _guess_assets(tag)
    match = [a for a in assets if pat.match(a["name"])]
    if not match:
        raise RuntimeError(
            f"No stable-diffusion.cpp build for {spec.os}/{backend} in release {tag}. "
            "Try Settings → Advanced → image backend = cpu, or check https://github.com/leejet/stable-diffusion.cpp/releases"
        )
    a = match[0]
    if job:
        job.phase = "image-engine"
        job.total = a["size"]
    say(f"Downloading image engine: {a['name']} ({(a['size'] or 0) / 2**20:.0f} MB, {backend})")
    dest = d / a["name"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=httpx.Timeout(60, read=600),
        follow_redirects=True,
        headers={"User-Agent": "datas.ar"},
    ) as c:
        with c.stream("GET", a["url"]) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) or a["size"]
            done = 0
            with dest.open("wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    if job:
                        job.progress(done, total)
    with zipfile.ZipFile(dest) as z:
        z.extractall(d)
    dest.unlink(missing_ok=True)
    exe = binary(d)
    if not exe:
        raise RuntimeError("The release archive did not contain sd-server")
    if sys.platform != "win32":
        for f in d.rglob("*"):
            if f.is_file() and (f.name.startswith("sd-") or f.suffix in (".so", ".dylib")):
                f.chmod(f.stat().st_mode | 0o111)
    # Windows CUDA builds need NVIDIA's runtime DLLs shipped as a separate archive
    if backend == "cuda" and spec.os == "windows":
        cud = [x for x in assets if x["name"].startswith("cudart-sd-bin-win")]
        if cud:
            say(
                f"Downloading CUDA runtime: {cud[0]['name']} ({(cud[0]['size'] or 0) / 2**20:.0f} MB)"
            )
            cdest = d / cud[0]["name"]
            with httpx.Client(timeout=httpx.Timeout(60, read=900), follow_redirects=True) as c:
                with c.stream("GET", cud[0]["url"]) as r:
                    r.raise_for_status()
                    with cdest.open("wb") as fh:
                        for chunk in r.iter_bytes(1 << 20):
                            fh.write(chunk)
            with zipfile.ZipFile(cdest) as z:
                z.extractall(exe.parent)
            cdest.unlink(missing_ok=True)
    say(f"Image engine ready: {exe}")
    return exe


# ---------------------------------------------------------------------------
# which model files


@dataclass
class ImageChoice:
    recipe: str  # z-image-turbo
    diffusion: dict  # {repo, file, bytes}
    text_encoder: dict
    vae: dict
    backend: str
    offload: bool  # weights kept in RAM and streamed to the GPU
    device: str  # gpu | unified | cpu
    total_bytes: int
    need_gib: float  # RAM (or VRAM when not offloading) while generating
    speed: str  # fast | ok | slow | crawl
    fits: bool = True  # False → the UI says so and why; the user may still try ("force")
    kind: str = "image"  # image | video
    te_flag: str = "--llm"  # how sd-server takes this recipe's text encoder
    reasons: list[str] = field(default_factory=list)

    def files(self) -> list[dict]:
        return [self.diffusion, self.text_encoder, self.vae]

    def plain(self, lang: str = "en") -> dict:
        r = recipe_of(self)
        return {
            "name": r["name"],
            "maker": r["maker"],
            "page": r["page"],
            "license": r["license"],
            "download": f"{self.total_bytes / GiB:.1f} GB",
            "memory": f"{self.need_gib:.1f} GB",
            "what": r["plain_es" if lang == "es" else "plain_en"],
            "limits": r["limits_es" if lang == "es" else "limits_en"],
            "speed": self.speed,
            "where": {
                "gpu": "runs on the graphics card",
                "unified": "runs on the graphics part of the chip (shared memory)",
                "cpu": "runs on the processor only",
            }[self.device],
        }


def choose(spec: DeviceSpec, cfg: Config | None = None) -> ImageChoice:
    cat = catalog()
    r = cat["recipes"]["z-image-turbo"]
    vram = spec.dedicated_vram_total / GiB
    unified = any(g.unified for g in spec.gpus)
    ram = spec.ram_total / GiB
    backend = backend_for(spec, cfg)
    reasons: list[str] = []
    # quantisation of the diffusion model by the memory that will hold it
    if vram >= 12 or (unified and ram >= 32):
        q, te = "Q8_0", "Q8_0"
        reasons.append(
            "Plenty of graphics memory: best quality (Q8_0) for picture and text encoder."
        )
    elif vram >= 8 or (unified and ram >= 16):
        q, te = "Q4_K", "Q4_K_M"
        reasons.append("Mid-size graphics memory: balanced quality (Q4_K).")
    else:
        q, te = "Q3_K", "Q4_K_M"
        reasons.append("Small memory: compact picture model (Q3_K); still 1024-px images.")
    diffusion = next(f for f in r["diffusion"]["files"] if f["quant"] == q)
    text_encoder = next(f for f in r["text_encoder"]["files"] if f["quant"] == te)
    vae = r["vae"]["files"][0]
    total = diffusion["bytes"] + text_encoder["bytes"] + vae["bytes"]
    working = 1.5  # GiB: latents, attention buffers at 1024 px
    need = total / GiB + working
    fits = True
    if vram >= need + 1 and not unified:  # 1 GB margin for the display and the OS
        device, offload, speed = "gpu", False, "fast" if vram >= 12 else "ok"
        reasons.append(f"Everything fits in the {vram:.0f} GB graphics card.")
    elif vram >= 4:
        device, offload, speed = "gpu", True, "ok" if vram >= 6 else "slow"
        reasons.append(
            f"Weights stay in RAM and stream to the {vram:.0f} GB graphics card (offload); "
            "a picture takes longer."
        )
        fits = ram >= total / GiB + 2
    elif unified:
        device, offload, speed = "unified", False, "ok" if ram >= 16 else "slow"
        reasons.append("Shared memory chip: the graphics part works from the same RAM.")
        fits = ram >= need + 2
    else:
        device, offload, speed = "cpu", False, "crawl" if ram < 16 else "slow"
        reasons.append(
            "No usable graphics card: the processor does it alone — expect minutes per image."
        )
        fits = ram >= need + 2
    if not fits:
        reasons.append(
            "Not enough memory to hold the picture model next to the rest of the computer."
        )
    for f, label in (
        (diffusion, r["diffusion"]),
        (text_encoder, r["text_encoder"]),
        (vae, r["vae"]),
    ):
        f.setdefault("repo", label["repo"])
    return ImageChoice(
        recipe="z-image-turbo",
        diffusion=diffusion,
        text_encoder=text_encoder,
        vae=vae,
        backend=backend,
        offload=offload,
        device=device,
        total_bytes=total,
        need_gib=round(need, 1),
        speed=speed,
        fits=fits,
        reasons=reasons,
    )


def choose_video(spec: DeviceSpec, cfg: Config | None = None) -> ImageChoice:
    """Wan 2.2 TI2V 5B: quantisation by graphics memory; never refused, only rated."""
    r = media()["video"]["recipes"]["wan2.2-ti2v-5b"]
    vram = spec.dedicated_vram_total / GiB
    unified = any(g.unified for g in spec.gpus)
    ram = spec.ram_total / GiB
    reasons: list[str] = []
    if vram >= 16 or (unified and ram >= 48):
        q, te = "Q8_0", "Q8_0"
        reasons.append("Plenty of graphics memory: best quality (Q8_0).")
    elif vram >= 10 or (unified and ram >= 24):
        q, te = "Q4_K_M", "Q4_K_M"
        reasons.append("Mid-size graphics memory: balanced quality (Q4_K_M).")
    else:
        q, te = "Q3_K_S", "Q3_K_M"
        reasons.append("Small memory: the most compact files (Q3).")
    diffusion = dict(
        next(f for f in r["diffusion"]["files"] if f["quant"] == q), repo=r["diffusion"]["repo"]
    )
    text_encoder = dict(
        next(f for f in r["text_encoder"]["files"] if f["quant"] == te),
        repo=r["text_encoder"]["repo"],
    )
    vae = dict(r["vae"]["files"][0], repo=r["vae"]["repo"])
    total = diffusion["bytes"] + text_encoder["bytes"] + vae["bytes"]
    need = total / GiB + 3.0  # video latents + VAE decode are heavy
    if vram >= need + 1 and not unified:
        device, offload, speed, fits = "gpu", False, "ok" if vram >= 16 else "slow", True
        reasons.append(f"Everything fits in the {vram:.0f} GB graphics card; a clip takes minutes.")
    elif vram >= 6:
        device, offload, speed = "gpu", True, "slow"
        fits = ram >= total / GiB + 2
        reasons.append(
            f"Weights stream from RAM to the {vram:.0f} GB graphics card; a clip takes many minutes."
        )
    elif unified:
        device, offload, speed = "unified", False, "slow"
        fits = ram >= need + 4
        reasons.append("Shared-memory chip: works from the same RAM; a clip takes many minutes.")
    else:
        device, offload, speed = "cpu", False, "crawl"
        fits = ram >= need + 2
        reasons.append("No usable graphics card: the processor alone needs hours per clip.")
    if not fits:
        reasons.append(
            "Not enough memory for the video model next to the rest of the computer — you can still try."
        )
    return ImageChoice(
        recipe="wan2.2-ti2v-5b",
        diffusion=diffusion,
        text_encoder=text_encoder,
        vae=vae,
        backend=backend_for(spec, cfg),
        offload=offload,
        device=device,
        total_bytes=total,
        need_gib=round(need, 1),
        speed=speed,
        fits=fits,
        kind="video",
        te_flag=r["text_encoder"].get("flag", "--t5xxl"),
        reasons=reasons,
    )


def local_path(f: dict) -> Path:
    return models_dir() / Path(f["file"]).name


def installed_files(choice: ImageChoice) -> dict:
    present = [
        f["file"]
        for f in choice.files()
        if local_path(f).exists() and local_path(f).stat().st_size == f["bytes"]
    ]
    return {"present": present, "ready": len(present) == 3}


def ensure_models(choice: ImageChoice, job: Job | None = None) -> list[Path]:
    say = job.say if job else print
    if job:
        job.phase = "image-models"
        job.total = choice.total_bytes
    base = 0
    out = []
    for f in choice.files():

        def prog(done: int, total: int | None, base=base) -> None:
            if job:
                job.progress(base + done, choice.total_bytes)

        say(f"{f['file']} ({f['bytes'] / GiB:.2f} GB) from {f['repo']}")
        out.append(
            downloader.download_file(
                f["repo"],
                f["file"],
                local_path(f),
                expected_size=f["bytes"],
                progress=prog,
                log=say,
            )
        )
        base += f["bytes"]
    return out


# ---------------------------------------------------------------------------
# the server


@dataclass
class SdState:
    pid: int | None = None
    port: int | None = None
    recipe: str | None = None
    started_at: float | None = None
    log_path: str | None = None
    args: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__ | {"running": self.pid is not None}


class SdServer:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.state = SdState()
        self._log_fh = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def args(self, choice: ImageChoice, spec: DeviceSpec, port: int) -> list[str]:
        a = [
            "--diffusion-model",
            str(local_path(choice.diffusion)),
            choice.te_flag,
            str(local_path(choice.text_encoder)),
            "--vae",
            str(local_path(choice.vae)),
            "--listen-ip",
            "127.0.0.1",
            "--listen-port",
            str(port),
            "--diffusion-fa",
            "-t",
            str(max(1, (spec.cpu_cores_physical or 2) - 1)),
        ]
        if choice.offload:
            a.append("--offload-to-cpu")
        if choice.device == "cpu":
            a += ["--backend", "cpu"]
        return a

    def start(
        self, exe: Path, choice: ImageChoice, spec: DeviceSpec, port: int, timeout: float = 900
    ) -> SdState:
        if self.running():
            self.stop()
        args = self.args(choice, spec, port)
        quiet = self.cfg.forget or not self.cfg.keep_logs
        log_path = logs_dir() / "sd-server.log"
        self._log_fh = open(os.devnull, "ab") if quiet else log_path.open("ab")
        env = os.environ.copy()
        libdir = str(exe.parent)
        if sys.platform.startswith("linux"):
            env["LD_LIBRARY_PATH"] = libdir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        elif sys.platform == "darwin":
            env["DYLD_LIBRARY_PATH"] = libdir + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
        creation = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {}
        )
        self._log_fh.write(
            f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {exe} {' '.join(args)}\n".encode()
        )
        self._log_fh.flush()
        self.proc = subprocess.Popen(
            [str(exe), *args],
            stdout=self._log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(exe.parent),
            **creation,
        )
        self.state = SdState(
            pid=self.proc.pid,
            port=port,
            recipe=choice.recipe,
            started_at=time.time(),
            log_path=None if quiet else str(log_path),
            args=args,
        )
        self.wait_ready(timeout)
        return self.state

    def wait_ready(self, timeout: float) -> None:
        deadline = time.time() + timeout
        url = f"http://127.0.0.1:{self.state.port}/sdcpp/v1/models/status"
        last = ""
        with httpx.Client(timeout=5, trust_env=False) as c:
            while time.time() < deadline:
                if self.proc and self.proc.poll() is not None:
                    raise RuntimeError(
                        f"sd-server exited with code {self.proc.returncode}; see {self.state.log_path or 'logs (disabled)'}"
                    )
                try:
                    j = c.get(url).json()
                    last = j.get("state", "")
                    if last == "ready":
                        return
                    if last == "error":
                        raise RuntimeError(f"sd-server could not load the models: {j.get('error')}")
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(1)
        raise TimeoutError(
            f"sd-server did not become ready in {timeout:.0f}s (last state: {last!r})"
        )

    def stop(self, grace: float = 10.0) -> None:
        if self.running():
            try:
                if sys.platform == "win32":
                    self.proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[union-attr]
                else:
                    self.proc.terminate()  # type: ignore[union-attr]
                self.proc.wait(grace)  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                self.proc.kill()  # type: ignore[union-attr]
        if self._log_fh:
            try:
                self._log_fh.close()
            except Exception:  # noqa: BLE001
                pass
        self._log_fh = None
        self.proc = None
        self.state = SdState()

    # ---- generation ------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        negative: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 8,
        cfg_scale: float = 1.0,
        seed: int = -1,
        progress=None,  # noqa: ANN001 - callable(done, total)
        timeout: float = 1800,
    ) -> list[bytes]:
        """Z-Image-Turbo defaults: 8 steps, CFG 1.0. Returns PNG bytes (never written here)."""
        base = f"http://127.0.0.1:{self.state.port}"
        body: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative,
            "width": int(width),
            "height": int(height),
            "seed": int(seed),
            "batch_count": 1,
            "sample_params": {
                "sample_method": "euler",
                "sample_steps": int(steps),
                "guidance": {"txt_cfg": float(cfg_scale)},
            },
        }
        with httpx.Client(timeout=httpx.Timeout(30, read=120), trust_env=False) as c:
            r = c.post(f"{base}/sdcpp/v1/img_gen", json=body)
            if r.status_code >= 400:
                raise RuntimeError(
                    f"sd-server refused the request: HTTP {r.status_code} {r.text[:300]}"
                )
            jid = r.json()["id"]
            deadline = time.time() + timeout
            while time.time() < deadline:
                j = c.get(f"{base}/sdcpp/v1/jobs/{jid}").json()
                st = j.get("status")
                p = j.get("progress") or {}
                if progress and p:
                    progress(int(p.get("step", 0) or 0), int(p.get("total_steps", steps) or steps))
                if st == "completed":
                    return [base64.b64decode(im["b64_json"]) for im in j["result"]["images"]]
                if st in ("failed", "cancelled"):
                    raise RuntimeError(f"image generation {st}: {j.get('error') or ''}")
                time.sleep(0.7)
        raise TimeoutError("image generation took too long")

    def generate_video(
        self,
        prompt: str,
        negative: str = "",
        width: int = 832,
        height: int = 480,
        frames: int = 33,
        fps: int = 16,
        steps: int = 20,
        cfg_scale: float = 6.0,
        flow_shift: float = 3.0,
        seed: int = -1,
        init_image_b64: str | None = None,
        progress=None,  # noqa: ANN001
        timeout: float = 6 * 3600,
    ) -> tuple[bytes, str]:
        """Text→video, or picture→video when ``init_image_b64`` is given. Returns (bytes, mime)."""
        base = f"http://127.0.0.1:{self.state.port}"
        body: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative,
            "width": int(width),
            "height": int(height),
            "seed": int(seed),
            "video_frames": int(frames),
            "fps": int(fps),
            "output_format": "webm",
            "sample_params": {
                "sample_method": "euler",
                "sample_steps": int(steps),
                "flow_shift": float(flow_shift),
                "guidance": {"txt_cfg": float(cfg_scale)},
            },
        }
        if init_image_b64:
            body["init_image"] = init_image_b64
        with httpx.Client(timeout=httpx.Timeout(30, read=300), trust_env=False) as c:
            r = c.post(f"{base}/sdcpp/v1/vid_gen", json=body)
            if r.status_code == 400 and "output_format" in r.text:  # build without WebM support
                body["output_format"] = "avi"
                r = c.post(f"{base}/sdcpp/v1/vid_gen", json=body)
            if r.status_code >= 400:
                raise RuntimeError(
                    f"sd-server refused the request: HTTP {r.status_code} {r.text[:300]}"
                )
            jid = r.json()["id"]
            deadline = time.time() + timeout
            while time.time() < deadline:
                j = c.get(f"{base}/sdcpp/v1/jobs/{jid}").json()
                st = j.get("status")
                p = j.get("progress") or {}
                if progress and p:
                    progress(int(p.get("step", 0) or 0), int(p.get("total_steps", steps) or steps))
                if st == "completed":
                    res = j["result"]
                    return base64.b64decode(res["b64_json"]), res.get("mime_type", "video/webm")
                if st in ("failed", "cancelled"):
                    raise RuntimeError(f"video generation {st}: {j.get('error') or ''}")
                time.sleep(1.5)
        raise TimeoutError("video generation took too long")
