import re

from datas.hardware.detect import GPU
from datas.runtime.llamacpp import _companions, _match, _probe_names, asset_patterns
from tests.conftest import G, spec

# Real asset list of release b11669 (Nov 2026)
B11669 = """llama-b11669-bin-macos-arm64.tar.gz llama-b11669-bin-macos-x64.tar.gz llama-b11669-xcframework.zip
llama-b11669-bin-ubuntu-x64.tar.gz llama-b11669-bin-ubuntu-arm64.tar.gz llama-b11669-bin-ubuntu-s390x.tar.gz
llama-b11669-bin-ubuntu-vulkan-x64.tar.gz llama-b11669-bin-ubuntu-vulkan-arm64.tar.gz
llama-b11669-bin-ubuntu-cuda-12.8-x64.tar.gz cudart-llama-b11669-bin-ubuntu-cuda-12.8-x64.tar.gz
llama-b11669-bin-ubuntu-cuda-13.4-x64.tar.gz cudart-llama-b11669-bin-ubuntu-cuda-13.4-x64.tar.gz
llama-b11669-bin-ubuntu-cuda-13.4-arm64.tar.gz cudart-llama-b11669-bin-ubuntu-cuda-13.4-arm64.tar.gz
llama-b11669-bin-ubuntu-rocm-10.0-x64.tar.gz llama-b11669-bin-ubuntu-openvino-2026.4.1-x64.tar.gz
llama-b11669-bin-ubuntu-sycl-fp32-x64.tar.gz llama-b11669-bin-ubuntu-sycl-fp16-x64.tar.gz
llama-b11669-bin-linux-arm64-snapdragon.tar.gz llama-b11669-bin-android-arm64.tar.gz
llama-b11669-bin-android-arm64-snapdragon.tar.gz llama-b11669-bin-win-cpu-x64.zip llama-b11669-bin-win-cpu-arm64.zip
llama-b11669-bin-win-opencl-adreno-arm64.zip llama-b11669-bin-win-cuda-12.4-x64.zip cudart-llama-bin-win-cuda-12.4-x64.zip
llama-b11669-bin-win-cuda-13.4-x64.zip cudart-llama-bin-win-cuda-13.4-x64.zip llama-b11669-bin-win-cuda-13.4-arm64.zip
cudart-llama-bin-win-cuda-13.4-arm64.zip llama-b11669-bin-win-vulkan-x64.zip llama-b11669-bin-win-vulkan-arm64.zip
llama-b11669-bin-win-openvino-2026.4.1-x64.zip llama-b11669-bin-win-sycl-x64.zip llama-b11669-bin-win-rocm-10.0-x64.zip
llama-b11669-ui.tar.gz""".split()
ASSETS = [{"name": n, "browser_download_url": "https://x/" + n} for n in B11669]


def pick(s, backend):
    a = _match(ASSETS, asset_patterns(s, backend))
    return a["name"] if a else None


def test_linux_variants():
    assert pick(spec(), "cpu") == "llama-b11669-bin-ubuntu-x64.tar.gz"
    assert (
        pick(spec(gpus=[GPU("amd", "x", 8 * G, None, False, "rocm")]), "rocm")
        == "llama-b11669-bin-ubuntu-rocm-10.0-x64.tar.gz"
    )
    assert (
        pick(spec(gpus=[GPU("intel", "x", None, None, True, "vulkan")]), "vulkan")
        == "llama-b11669-bin-ubuntu-vulkan-x64.tar.gz"
    )
    cuda = pick(spec(gpus=[GPU("nvidia", "x", 8 * G, None, False, "cuda")]), "cuda")
    assert re.fullmatch(r"llama-b11669-bin-ubuntu-cuda-1[23]\.\d-x64\.tar\.gz", cuda)
    assert _companions(ASSETS, cuda) == [(f"cudart-{cuda}", f"https://x/cudart-{cuda}")]


def test_windows_variants():
    cuda = pick(spec("windows", gpus=[GPU("nvidia", "x", 8 * G, None, False, "cuda")]), "cuda")
    assert cuda.startswith("llama-b11669-bin-win-cuda-")
    comp = _companions(ASSETS, cuda)
    assert len(comp) == 1 and comp[0][0].startswith("cudart-llama-bin-win-cuda-")
    assert pick(spec("windows"), "cpu") == "llama-b11669-bin-win-cpu-x64.zip"
    assert (
        pick(
            spec("windows", "arm64", gpus=[GPU("qualcomm", "x", None, None, True, "opencl")]),
            "opencl",
        )
        == "llama-b11669-bin-win-opencl-adreno-arm64.zip"
    )


def test_mac_and_android():
    assert pick(spec("darwin", "arm64"), "metal") == "llama-b11669-bin-macos-arm64.tar.gz"
    assert pick(spec("darwin", "x86_64"), "metal") == "llama-b11669-bin-macos-x64.tar.gz"
    assert pick(spec("android", "arm64"), "vulkan") == "llama-b11669-bin-android-arm64.tar.gz"
    assert (
        pick(
            spec("android", "arm64", gpus=[GPU("qualcomm", "sm8650", None, None, True, "opencl")]),
            "opencl",
        )
        == "llama-b11669-bin-android-arm64-snapdragon.tar.gz"
    )


def test_probe_names_are_concrete_and_ordered():
    names = _probe_names(
        spec("windows", gpus=[GPU("nvidia", "x", 8 * G, None, False, "cuda")]), "cuda", "b11669"
    )
    assert names[0].startswith("llama-b11669-bin-win-cuda-")
    assert "llama-b11669-bin-win-vulkan-x64.zip" in names
    assert names[-1] == "llama-b11669-bin-win-cpu-x64.zip"
    assert all("\\" not in n and "(" not in n for n in names)
