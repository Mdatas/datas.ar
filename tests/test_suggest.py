"""'Try this AI instead': faster, or able to do what the current AI cannot, and always fitting."""

from datas.catalog import load
from datas.hardware.detect import GPU, DeviceSpec
from datas.recommend import suggest as S
from datas.recommend.engine import recommend


def _spec(ram_gib: float) -> DeviceSpec:
    return DeviceSpec(
        os="linux",
        os_version="test",
        hostname="test",
        cpu_flags=[],
        swap_total=0,
        arch="x86_64",
        cpu_name="test",
        cpu_cores_physical=4,
        cpu_cores_logical=8,
        ram_total=int(ram_gib * 2**30),
        ram_available=int(ram_gib * 2**30),
        disk_free_models=500 * 2**30,
        gpus=[],
        form_factor="laptop",
    )


def test_faster_is_smaller_and_fits():
    rec = recommend(_spec(16), load())
    big = load().get("qwen3-8b")
    out = S.faster(rec, big.id, big.files[0].bytes, set())
    assert "model_id" in out and out["model_id"] != big.id
    assert out["gib"] * 2**30 <= 0.6 * big.files[0].bytes + 2**30


def test_smallest_already_says_so():
    rec = recommend(_spec(16), load())
    tiny = load().get("qwen3-0.6b")
    assert "none" in S.faster(rec, tiny.id, tiny.files[0].bytes, set())


def test_an_ai_that_sees_on_a_mid_laptop_and_none_on_a_tiny_device():
    out = S.able(recommend(_spec(16), load(), want=["vision"]), "vision", set())
    assert "vision" in load().get(out["model_id"]).capabilities
    none = S.able(recommend(_spec(1), load(), want=["vision"]), "vision", set())
    assert none["none"].startswith("No AI that can see pictures")


def test_one_already_here_is_preferred_when_nearly_as_good():
    rec = recommend(_spec(16), load(), want=["tools"])
    here = rec.fits[-1].model_id
    out = S.able(rec, "tools", {here})
    assert out["installed"] or out["model_id"] == rec.default.model_id


_ = GPU  # the device above has no graphics card
