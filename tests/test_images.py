"""Image engine: recipe catalog integrity, per-device choices, release asset patterns and the
sd-server argument builder. Network-free."""

from __future__ import annotations

import re

from datas.config import Config
from datas.engines import images
from datas.hardware.detect import GPU
from tests.conftest import spec

G = 2**30

# the exact asset names of the pinned release (verified 2026-11-09)
ASSETS = [
    "cudart-sd-bin-win-cu12-x64.zip",
    "sd-master-2f88688-bin-Darwin-macOS-26.6.2-arm64.zip",
    "sd-master-2f88688-bin-Linux-Ubuntu-24.04-x86_64-rocm-7.14.0.zip",
    "sd-master-2f88688-bin-Linux-Ubuntu-24.04-x86_64-vulkan.zip",
    "sd-master-2f88688-bin-Linux-Ubuntu-24.04-x86_64.zip",
    "sd-master-2f88688-bin-win-cpu-x64.zip",
    "sd-master-2f88688-bin-win-cuda12-x64.zip",
    "sd-master-2f88688-bin-win-rocm-7.14.0-x64.zip",
    "sd-master-2f88688-bin-win-vulkan-x64.zip",
]


def test_recipe_catalog_is_complete():
    cat = images.catalog()
    r = cat["recipes"]["z-image-turbo"]
    assert {f["quant"] for f in r["diffusion"]["files"]} == {"Q3_K", "Q4_K", "Q8_0"}
    assert all(f["bytes"] > 10**9 for f in r["diffusion"]["files"])
    assert r["text_encoder"]["files"][0]["file"].startswith("Qwen3-4B-Instruct-2507")
    assert (
        r["vae"]["files"][0]["file"] == "ae.safetensors"
        and r["vae"]["files"][0]["bytes"] == 335304388
    )
    assert r["steps"] == 8 and r["cfg_scale"] == 1.0 and "plain_es" in r and "limits_en" in r


def test_asset_patterns_match_exactly_one_release_file():
    cases = [
        (spec(os_="windows", gpus=[]), "cpu", "sd-master-2f88688-bin-win-cpu-x64.zip"),
        (
            spec(os_="windows", gpus=[GPU("nvidia", "x", 8 * G, 7 * G, False, "cuda")]),
            "vulkan",
            "sd-master-2f88688-bin-win-vulkan-x64.zip",
        ),
        (
            spec(os_="windows", gpus=[GPU("nvidia", "x", 8 * G, 7 * G, False, "cuda")]),
            "cuda",
            "sd-master-2f88688-bin-win-cuda12-x64.zip",
        ),
        (
            spec(os_="windows", gpus=[GPU("amd", "x", 8 * G, 7 * G, False, "rocm")]),
            "rocm",
            "sd-master-2f88688-bin-win-rocm-7.14.0-x64.zip",
        ),
        (spec(os_="linux", gpus=[]), "cpu", "sd-master-2f88688-bin-Linux-Ubuntu-24.04-x86_64.zip"),
        (
            spec(os_="linux", gpus=[GPU("amd", "x", 8 * G, 7 * G, False, "vulkan")]),
            "vulkan",
            "sd-master-2f88688-bin-Linux-Ubuntu-24.04-x86_64-vulkan.zip",
        ),
        (
            spec(os_="linux", gpus=[GPU("amd", "x", 8 * G, 7 * G, False, "rocm")]),
            "rocm",
            "sd-master-2f88688-bin-Linux-Ubuntu-24.04-x86_64-rocm-7.14.0.zip",
        ),
        (
            spec(os_="darwin", arch="arm64", gpus=[GPU("apple", "M3", None, None, True, "metal")]),
            "metal",
            "sd-master-2f88688-bin-Darwin-macOS-26.6.2-arm64.zip",
        ),
    ]
    for s, backend, expected in cases:
        pat = re.compile(images.asset_pattern(s, backend))
        hits = [a for a in ASSETS if pat.match(a)]
        assert hits == [expected], (backend, hits)
    guessed = {a["name"] for a in images._guess_assets(images.KNOWN_GOOD_TAG)}
    assert guessed <= set(ASSETS)


def test_backend_choice():
    assert images.backend_for(spec(gpus=[])) == "cpu"
    assert (
        images.backend_for(spec(gpus=[GPU("nvidia", "x", 8 * G, 7 * G, False, "cuda")])) == "vulkan"
    )
    assert (
        images.backend_for(spec(os_="darwin", gpus=[GPU("apple", "M3", None, None, True, "metal")]))
        == "metal"
    )
    cfg = Config()
    cfg.image_backend = "cuda"
    assert (
        images.backend_for(spec(gpus=[GPU("nvidia", "x", 8 * G, 7 * G, False, "cuda")]), cfg)
        == "cuda"
    )


def test_choice_by_device_and_server_args():
    small = images.choose(spec(ram=8, cores=4, gpus=[]))
    assert small.device == "cpu" and not small.fits and small.speed == "crawl"
    cpu16 = images.choose(spec(ram=16, cores=8, gpus=[]))
    assert cpu16.fits and cpu16.diffusion["quant"] == "Q3_K" and cpu16.speed == "slow"
    mid = images.choose(
        spec(ram=16, cores=8, gpus=[GPU("nvidia", "RTX 4060", 8 * G, 7 * G, False, "cuda")])
    )
    assert mid.device == "gpu" and mid.offload and mid.diffusion["quant"] == "Q4_K" and mid.fits
    big = images.choose(
        spec(ram=64, cores=16, gpus=[GPU("nvidia", "RTX 4090", 24 * G, 23 * G, False, "cuda")])
    )
    assert (
        big.device == "gpu"
        and not big.offload
        and big.diffusion["quant"] == "Q8_0"
        and big.speed == "fast"
    )
    assert big.total_bytes == sum(f["bytes"] for f in big.files())
    p = big.plain("es")
    assert p["download"].endswith("GB") and "Z-Image" in p["name"]
    srv = images.SdServer(Config())
    args = srv.args(mid, spec(ram=16, cores=8), 8422)
    assert (
        "--offload-to-cpu" in args
        and "--diffusion-fa" in args
        and args[args.index("--listen-port") + 1] == "8422"
    )
    assert args[args.index("--diffusion-model") + 1].endswith("z_image_turbo-Q4_K.gguf")
    args_cpu = srv.args(cpu16, spec(ram=16, cores=8, gpus=[]), 8422)
    assert "--backend" in args_cpu and args_cpu[args_cpu.index("--backend") + 1] == "cpu"
