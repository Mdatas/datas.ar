import os
import tempfile

import pytest

# Keep every test away from the user's real Datas home — unless DATAS_HOME is set on
# purpose (that also lets the integration test find an installed llama.cpp runtime).
if not os.environ.get("DATAS_HOME"):
    os.environ["DATAS_HOME"] = tempfile.mkdtemp(prefix="datas-test-")

# The test client calls the app as "testserver"; the app answers only to local names.
os.environ.setdefault("DATAS_ALLOW_HOSTS", "testserver")
os.environ.setdefault("DATAS_NO_AUTO_UPDATE", "1")
os.environ.setdefault(
    "DATAS_NO_STARTER", "1"
)  # tests start no AI by themselves  # tests never reach the releases page

from datas.hardware.detect import GPU, DeviceSpec  # noqa: E402

G = 2**30


def spec(os_="linux", arch="x86_64", ram=16, gpus=None, form="desktop", cores=8, disk=200):
    return DeviceSpec(
        os=os_,
        os_version="x",
        arch=arch,
        hostname="h",
        cpu_name="cpu",
        cpu_cores_physical=cores,
        cpu_cores_logical=cores * 2,
        cpu_flags=["avx2"],
        ram_total=ram * G,
        ram_available=int(ram * 0.8) * G,
        swap_total=0,
        disk_free_models=disk * G,
        gpus=gpus or [],
        has_battery=form == "laptop",
        form_factor=form,
    )


@pytest.fixture
def vm8():
    return spec(ram=8, cores=2)


@pytest.fixture
def rtx4090_64():
    return spec(ram=64, cores=16, gpus=[GPU("nvidia", "RTX 4090", 24 * G, 23 * G, False, "cuda")])


@pytest.fixture
def mac36():
    return spec(
        "darwin",
        "arm64",
        ram=36,
        cores=12,
        gpus=[GPU("apple", "M3 Pro", None, None, True, "metal")],
        form="laptop",
    )


@pytest.fixture
def phone8():
    return spec(
        "android",
        "arm64",
        ram=8,
        cores=8,
        gpus=[GPU("qualcomm", "Adreno", None, None, True, "opencl")],
        form="phone",
        disk=50,
    )


@pytest.fixture
def laptop16_8():
    return spec(
        "windows",
        ram=16,
        cores=8,
        gpus=[GPU("nvidia", "RTX 4060 Laptop", 8 * G, 7 * G, False, "cuda")],
        form="laptop",
    )
