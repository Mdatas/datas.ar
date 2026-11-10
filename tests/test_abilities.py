"""The device verdicts: an old phone, a plain laptop, a gaming laptop, a Mac and a workstation
must each get honest, different answers — and no ability is ever hidden beforehand."""

from __future__ import annotations

from datas.catalog import load as load_catalog
from datas.hardware.detect import GPU
from datas.recommend.abilities import assess
from datas.recommend.engine import recommend
from tests.conftest import spec

G = 2**30
IDS = ["text", "images", "coding", "agents", "sound", "image_gen", "video"]


def verdicts(s, **kw):
    rec = recommend(s, load_catalog(), context=8192, **kw)
    out = {a.id: a for a in assess(s, rec)}
    assert [a for a in out if a in IDS] == IDS  # always the full list, same order
    for a in out.values():
        assert a.verdict in {"yes", "slow", "no", "not_yet"} and a.why and a.why_es
        if a.verdict == "no":
            assert a.needs and a.needs_es, a.id
    return {k: v.verdict for k, v in out.items()}


def test_old_phone_is_told_plainly():
    v = verdicts(spec(ram=3, cores=4, form="phone", disk=10, gpus=[]))
    assert v["image_gen"] == "no" and v["video"] == "no"
    assert v["sound"] == "not_yet"  # the phone app has no voice yet
    assert v["text"] in {"yes", "slow", "no"}


def test_plain_laptop_no_gpu():
    v = verdicts(spec(ram=8, cores=4, form="laptop", gpus=[]))
    assert v["text"] in {"yes", "slow"} and v["sound"] == "yes"
    assert v["image_gen"] == "no" and v["video"] == "no"
    # 16 GB and no GPU: possible on the processor, slowly
    assert verdicts(spec(ram=16, cores=8, gpus=[]))["image_gen"] == "slow"


def test_gaming_laptop_can_make_images_but_not_video_yet():
    v = verdicts(
        spec(ram=16, cores=8, gpus=[GPU("nvidia", "RTX 4060 Laptop", 8 * G, 7 * G, False, "cuda")])
    )
    assert v["image_gen"] == "yes" and v["video"] in {"yes", "slow"}  # 8 GB: borderline video
    assert v["agents"] in {"yes", "slow"}


def test_workstation_everything_possible():
    v = verdicts(
        spec(ram=64, cores=16, gpus=[GPU("nvidia", "RTX 4090", 24 * G, 23 * G, False, "cuda")])
    )
    assert (
        v["text"] == "yes"
        and v["images"] == "yes"
        and v["coding"] == "yes"
        and v["agents"] == "yes"
    )
    assert v["sound"] == "yes" and v["image_gen"] == "yes" and v["video"] in {"yes", "slow"}


def test_apple_silicon_unified_memory_counts():
    v = verdicts(
        spec(
            ram=36,
            cores=12,
            form="laptop",
            gpus=[GPU("apple", "M3 Pro", None, None, True, "metal")],
        )
    )
    assert v["image_gen"] == "yes" and v["video"] in {"yes", "slow"}


def test_voice_packages_missing_is_reported_not_hidden():
    s = spec(ram=16, cores=8, gpus=[])
    rec = recommend(s, load_catalog(), context=8192)
    a = {x.id: x for x in assess(s, rec, voice_available=False)}["sound"]
    assert a.verdict == "not_yet" and "reinstall" in a.why
