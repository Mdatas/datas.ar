"""Device detection.

Reads everything the recommender needs: OS, CPU (cores, ISA flags), RAM, every GPU with
its VRAM, disk space, power source and form factor. Detection is deterministic and uses
only what is actually present on the machine — psutil, py-cpuinfo and the vendor tools
(nvidia-smi / NVML, rocm-smi or sysfs, system_profiler, PowerShell CIM). Nothing is
guessed: when a value cannot be read it is left as None and reported as unknown.

Reuses: psutil (RAM/CPU/disk/battery), py-cpuinfo (ISA flags), nvidia-ml-py (NVML).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

GiB = 2**30


@dataclass
class GPU:
    vendor: str  # nvidia | amd | apple | intel | qualcomm | unknown
    name: str
    vram_total: int | None = None  # bytes; None when unknown
    vram_free: int | None = None
    unified: bool = False  # shares system RAM (Apple Silicon, iGPUs, phones)
    backend: str = "cpu"  # suggested llama.cpp backend: cuda | rocm | metal | vulkan | opencl | cpu
    driver: str | None = None
    source: str = ""  # how we read it (nvml, nvidia-smi, rocm-smi, sysfs, system_profiler, cim)

    @property
    def vram_gib(self) -> float | None:
        return None if self.vram_total is None else self.vram_total / GiB


@dataclass
class DeviceSpec:
    os: str  # linux | darwin | windows | android
    os_version: str
    arch: str  # x86_64 | arm64
    hostname: str
    cpu_name: str
    cpu_cores_physical: int
    cpu_cores_logical: int
    cpu_flags: list[str]
    ram_total: int
    ram_available: int
    swap_total: int
    disk_free_models: int
    gpus: list[GPU] = field(default_factory=list)
    on_battery: bool | None = None
    has_battery: bool = False
    form_factor: str = "desktop"  # phone | laptop | desktop | server
    python: str = sys.version.split()[0]
    notes: list[str] = field(default_factory=list)

    # ---- derived helpers -------------------------------------------------
    @property
    def ram_gib(self) -> float:
        return self.ram_total / GiB

    @property
    def best_gpu(self) -> GPU | None:
        dedicated = [g for g in self.gpus if g.vram_total and not g.unified]
        if dedicated:
            return max(dedicated, key=lambda g: g.vram_total or 0)
        unified = [g for g in self.gpus if g.unified]
        return unified[0] if unified else None

    @property
    def dedicated_vram_total(self) -> int:
        return sum(g.vram_total or 0 for g in self.gpus if g.vram_total and not g.unified)

    @property
    def suggested_backend(self) -> str:
        g = self.best_gpu
        return g.backend if g else "cpu"

    @property
    def has_avx2(self) -> bool:
        return "avx2" in self.cpu_flags

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ram_gib"] = round(self.ram_gib, 1)
        d["dedicated_vram_gib"] = round(self.dedicated_vram_total / GiB, 1)
        d["suggested_backend"] = self.suggested_backend
        for g in d["gpus"]:
            g["vram_gib"] = None if g["vram_total"] is None else round(g["vram_total"] / GiB, 1)
        return d


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: float = 8.0) -> str | None:
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        out = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0 and not out.stdout:
        return None
    return out.stdout


def _is_android() -> bool:
    return bool(os.environ.get("ANDROID_ROOT")) or Path("/system/build.prop").exists()


def _os_name() -> str:
    if _is_android():
        return "android"
    s = platform.system().lower()
    return {"darwin": "darwin", "windows": "windows", "linux": "linux"}.get(s, s)


def _arch() -> str:
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return m


def _cpu_info() -> tuple[str, list[str]]:
    name, flags = platform.processor() or "", []
    try:
        import cpuinfo  # py-cpuinfo

        info = cpuinfo.get_cpu_info()
        name = info.get("brand_raw") or name
        flags = sorted(set(info.get("flags", [])))
    except Exception:  # pragma: no cover - cpuinfo is optional at runtime
        pass
    if not name and _os_name() == "darwin":
        out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        name = (out or "").strip()
    if not name and Path("/proc/cpuinfo").exists():
        for line in Path("/proc/cpuinfo").read_text(errors="ignore").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                name = line.split(":", 1)[1].strip()
                break
    # Normalise the ISA flags we care about
    norm = set()
    for f in flags:
        f = f.lower()
        if f in ("avx", "avx2", "avx512f", "fma", "f16c", "neon", "asimd", "sve", "amx_tile"):
            norm.add("neon" if f == "asimd" else f)
    if _arch() == "arm64":
        norm.add("neon")
    return name or "unknown CPU", sorted(norm)


# ---- GPU detection --------------------------------------------------------


def _gpus_nvidia() -> list[GPU]:
    gpus: list[GPU] = []
    try:
        import pynvml  # nvidia-ml-py

        pynvml.nvmlInit()
        try:
            drv = pynvml.nvmlSystemGetDriverVersion()
            drv = drv.decode() if isinstance(drv, bytes) else str(drv)
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                name = name.decode() if isinstance(name, bytes) else str(name)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                gpus.append(
                    GPU("nvidia", name, int(mem.total), int(mem.free), False, "cuda", drv, "nvml")
                )
        finally:
            pynvml.nvmlShutdown()
        if gpus:
            return gpus
    except Exception:
        pass
    out = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if out:
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                try:
                    total = int(float(parts[1]) * 1024**2)
                    free = int(float(parts[2]) * 1024**2)
                except ValueError:
                    total = free = None
                gpus.append(
                    GPU(
                        "nvidia",
                        parts[0],
                        total,
                        free,
                        False,
                        "cuda",
                        parts[3] if len(parts) > 3 else None,
                        "nvidia-smi",
                    )
                )
    return gpus


def _gpus_amd_linux() -> list[GPU]:
    gpus: list[GPU] = []
    out = _run(["rocm-smi", "--showmeminfo", "vram", "--showproductname", "--json"])
    if out:
        try:
            data = json.loads(out)
            for _card, v in data.items():
                total = v.get("VRAM Total Memory (B)")
                used = v.get("VRAM Total Used Memory (B)")
                name = v.get("Card Series") or v.get("Card model") or "AMD GPU"
                t = int(total) if total else None
                f = (t - int(used)) if (t and used) else None
                gpus.append(GPU("amd", name, t, f, False, "rocm", None, "rocm-smi"))
            if gpus:
                return gpus
        except (json.JSONDecodeError, ValueError):
            pass
    # sysfs fallback (amdgpu exposes VRAM sizes without any tool installed)
    for dev in sorted(Path("/sys/class/drm").glob("card[0-9]*/device")):
        vendor = (dev / "vendor").read_text().strip() if (dev / "vendor").exists() else ""
        if vendor.lower() != "0x1002":
            continue
        tot = dev / "mem_info_vram_total"
        used = dev / "mem_info_vram_used"
        if not tot.exists():
            continue
        try:
            t = int(tot.read_text().strip())
            f = t - int(used.read_text().strip()) if used.exists() else None
        except ValueError:
            continue
        name = "AMD GPU"
        if (dev / "product_name").exists():
            name = (dev / "product_name").read_text().strip() or name
        # iGPUs report tiny carve-outs; mark as unified so RAM is counted instead
        unified = t < 2 * GiB
        gpus.append(GPU("amd", name, t, f, unified, "vulkan" if unified else "rocm", None, "sysfs"))
    return gpus


def _gpus_intel_linux() -> list[GPU]:
    gpus: list[GPU] = []
    for dev in sorted(Path("/sys/class/drm").glob("card[0-9]*/device")):
        vendor = (dev / "vendor").read_text().strip() if (dev / "vendor").exists() else ""
        if vendor.lower() != "0x8086":
            continue
        # Intel GPUs: dedicated VRAM is not exposed in a stable sysfs file; treat Arc as
        # vulkan-capable with unknown VRAM and iGPUs as unified.
        gpus.append(GPU("intel", "Intel GPU", None, None, True, "vulkan", None, "sysfs"))
    return gpus


def _gpus_apple() -> list[GPU]:
    out = _run(["system_profiler", "SPDisplaysDataType", "-json"], timeout=20)
    gpus: list[GPU] = []
    if out:
        try:
            data = json.loads(out)
            for item in data.get("SPDisplaysDataType", []):
                name = item.get("sppci_model") or item.get("_name") or "Apple GPU"
                vram_s = item.get("spdisplays_vram") or item.get("spdisplays_vram_shared")
                vram = None
                if vram_s:
                    m = re.match(r"\s*(\d+)\s*(MB|GB)", vram_s)
                    if m:
                        vram = int(m.group(1)) * (GiB if m.group(2) == "GB" else 1024**2)
                is_apple_silicon = "Apple" in name or _arch() == "arm64"
                gpus.append(
                    GPU(
                        "apple" if is_apple_silicon else "amd",
                        name,
                        None if is_apple_silicon else vram,
                        None,
                        is_apple_silicon,
                        "metal",
                        None,
                        "system_profiler",
                    )
                )
        except json.JSONDecodeError:
            pass
    if not gpus and _arch() == "arm64":
        gpus.append(GPU("apple", "Apple Silicon GPU", None, None, True, "metal", None, "arch"))
    return gpus


def _gpus_windows() -> list[GPU]:
    # CIM gives names reliably; AdapterRAM is a 32-bit field and under-reports >4 GB, so
    # we only use it for the vendor split and prefer nvidia-smi for NVIDIA cards.
    ps = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json",
    ]
    out = _run(ps, timeout=20)
    gpus: list[GPU] = []
    if not out:
        return gpus
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return gpus
    if isinstance(data, dict):
        data = [data]
    for d in data:
        name = str(d.get("Name", "GPU"))
        low = name.lower()
        if "nvidia" in low:
            continue  # handled by NVML/nvidia-smi
        if "amd" in low or "radeon" in low:
            vendor, backend, unified = (
                "amd",
                "vulkan",
                "graphics" in low and "radeon" in low and "rx" not in low,
            )
        elif "intel" in low:
            vendor, backend, unified = "intel", "vulkan", "arc" not in low
        elif "qualcomm" in low or "adreno" in low:
            vendor, backend, unified = "qualcomm", "opencl", True
        else:
            vendor, backend, unified = "unknown", "vulkan", False
        ram = d.get("AdapterRAM")
        vram = int(ram) if isinstance(ram, (int, float)) and ram > 0 and ram < 4 * GiB else None
        gpus.append(
            GPU(
                vendor, name, vram, None, unified, backend, str(d.get("DriverVersion") or ""), "cim"
            )
        )
    return gpus


def _gpus_android() -> list[GPU]:
    # Phones: GPU shares RAM. llama.cpp offers OpenCL (Adreno) and Vulkan builds.
    soc = _run(["getprop", "ro.soc.model"]) or _run(["getprop", "ro.hardware"]) or ""
    soc = soc.strip() or "mobile SoC"
    backend = (
        "opencl"
        if "adreno" in soc.lower() or "sm" in soc.lower() or "qualcomm" in soc.lower()
        else "vulkan"
    )
    return [
        GPU(
            "qualcomm" if backend == "opencl" else "unknown",
            soc,
            None,
            None,
            True,
            backend,
            None,
            "getprop",
        )
    ]


def detect_gpus(os_name: str) -> list[GPU]:
    gpus: list[GPU] = []
    if os_name == "android":
        return _gpus_android()
    gpus += _gpus_nvidia()
    if os_name == "linux":
        gpus += _gpus_amd_linux()
        gpus += _gpus_intel_linux()
    elif os_name == "darwin":
        gpus += _gpus_apple()
    elif os_name == "windows":
        gpus += _gpus_windows()
    return gpus


# ---- form factor / power ---------------------------------------------------


def _battery() -> tuple[bool, bool | None]:
    try:
        b = psutil.sensors_battery()
    except Exception:
        return False, None
    if b is None:
        return False, None
    return True, (not b.power_plugged)


def _form_factor(os_name: str, has_battery: bool, ram: int, cores: int) -> str:
    if os_name == "android":
        return "phone"
    if has_battery:
        return "laptop"
    if cores >= 32 and ram >= 128 * GiB:
        return "server"
    return "desktop"


# ---------------------------------------------------------------------------


def detect(models_path: Path | None = None) -> DeviceSpec:
    os_name = _os_name()
    cpu_name, flags = _cpu_info()
    vm = psutil.virtual_memory()
    try:
        swap_total = int(psutil.swap_memory().total)
    except Exception:  # noqa: BLE001 - Windows: "PdhAddEnglishCounterW failed" when perf counters are off
        swap_total = 0
    phys = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
    logical = psutil.cpu_count() or phys
    if models_path is None:
        from datas.config import models_dir

        models_path = models_dir()
    try:
        disk_free = shutil.disk_usage(models_path).free
    except OSError:
        disk_free = 0
    has_batt, on_batt = _battery()
    gpus = detect_gpus(os_name)
    notes: list[str] = []
    if os_name == "linux" and os.environ.get("WSL_DISTRO_NAME"):
        notes.append("Running under WSL: GPU access depends on the Windows driver's WSL support.")
    if not gpus:
        notes.append(
            "No GPU detected; CPU inference. Vulkan may still work if a driver is present."
        )
    for g in gpus:
        if g.unified:
            notes.append(f"{g.name}: shares system RAM (unified memory); RAM is the budget.")
    if os_name == "windows" and _arch() == "x86_64" and "avx2" not in flags:
        notes.append("CPU lacks AVX2: llama.cpp CPU builds will be slow; prefer a GPU backend.")
    spec = DeviceSpec(
        os=os_name,
        os_version=platform.platform(),
        arch=_arch(),
        hostname=platform.node(),
        cpu_name=cpu_name,
        cpu_cores_physical=int(phys),
        cpu_cores_logical=int(logical),
        cpu_flags=flags,
        ram_total=int(vm.total),
        ram_available=int(vm.available),
        swap_total=swap_total,
        disk_free_models=int(disk_free),
        gpus=gpus,
        on_battery=on_batt,
        has_battery=has_batt,
        form_factor=_form_factor(os_name, has_batt, int(vm.total), int(logical)),
        notes=notes,
    )
    return spec


if __name__ == "__main__":  # quick manual check: python -m datas.hardware.detect
    print(json.dumps(detect().to_dict(), indent=2))
