# Hardware detection

`datas/hardware/detect.py` → `DeviceSpec`. Run `datas scan --json` to see the raw result.
Nothing is guessed: a value that cannot be read is `null` and shows as "unknown".

## What is read

| Field | Source | Notes |
|---|---|---|
| `os`, `os_version`, `arch` | `platform`, `/system/build.prop` or `ANDROID_ROOT` for Android | `arch` normalised to `x86_64` / `arm64` |
| `cpu_name`, `cpu_flags` | `py-cpuinfo`; fallbacks `sysctl machdep.cpu.brand_string` (macOS), `/proc/cpuinfo` | flags reduced to the ones that matter for llama.cpp: avx, avx2, avx512f, fma, f16c, amx_tile, neon, sve |
| `cpu_cores_physical/logical` | `psutil.cpu_count` | |
| `ram_total`, `ram_available`, `swap_total` | `psutil.virtual_memory/swap_memory` | budget uses *total* minus headroom; `available` is shown as a hint |
| `disk_free_models` | `shutil.disk_usage(models_dir)` | the disk the models land on |
| `gpus[]` | see below | |
| `has_battery`, `on_battery` | `psutil.sensors_battery` | laptops → `form_factor=laptop` |
| `form_factor` | derived: android→phone, battery→laptop, ≥32 cores & ≥128 GiB→server, else desktop | drives the default headroom |

## GPUs, per vendor / OS

| Vendor | Method (in order) | VRAM | Backend hint |
|---|---|---|---|
| NVIDIA (all OS) | `nvidia-ml-py` (NVML) → `nvidia-smi --query-gpu=…` | total + free | `cuda` |
| AMD, Linux | `rocm-smi --json` → sysfs `/sys/class/drm/card*/device/mem_info_vram_*` | total (+used) | `rocm` (dGPU) / `vulkan` (iGPU, <2 GiB carve-out → treated as unified) |
| AMD, Windows | PowerShell `Get-CimInstance Win32_VideoController` | *not trusted* (32-bit field) → unknown | `vulkan` |
| Intel, Linux | sysfs vendor `0x8086` | unknown | `vulkan`, unified unless Arc |
| Intel, Windows | CIM | unknown | `vulkan` |
| Apple Silicon | `system_profiler SPDisplaysDataType -json`; arch fallback | unified (RAM is the budget) | `metal` |
| Qualcomm / Android | `getprop ro.soc.model` | unified | `opencl` (Adreno) else `vulkan` |

When VRAM is unknown for a dedicated GPU, the recommender treats the GPU as absent
for *memory* purposes (CPU/RAM budget) but still passes the backend so llama.cpp can
offload with `-ngl auto --fit on`; the `notes` field tells the user why.

## Notes the scanner emits

- No GPU detected → CPU inference (Vulkan may still work if a driver exists).
- Unified-memory GPU → "RAM is the budget".
- WSL → GPU depends on the Windows driver's WSL support.
- x86 without AVX2 → CPU builds will be slow.

## Adding a detector

Add a `_gpus_<vendor>()` returning `list[GPU]` and call it from `detect_gpus()`. Keep the
rule: read, don't infer. If a tool is missing, return `[]` and let the next method try.
