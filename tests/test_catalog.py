import json

from datas.catalog import BITS_PER_WEIGHT, bundled_path, load


def test_catalog_loads_and_validates():
    cat = load()
    assert len(cat.models) >= 15
    ids = cat.ids()
    assert len(ids) == len(set(ids)), "duplicate model ids"


def test_every_file_has_verified_size_and_known_quant():
    for m in load().models:
        assert m.hf_repo.count("/") == 1
        for f in m.files:
            assert f.bytes > 10 * 2**20, f"{m.id} {f.quant} suspiciously small"
            assert f.verified, f"{m.id} {f.quant} has no verification date"
            assert f.path.endswith(".gguf")
            assert f.quant.upper() in BITS_PER_WEIGHT, f"unknown quant {f.quant} for {m.id}"


def test_quants_sorted_by_size_within_model():
    # smaller quant must have fewer bytes — catches copy/paste mistakes in sizes
    for m in load().models:
        by_bpw = sorted(m.files, key=lambda f: BITS_PER_WEIGHT[f.quant.upper()])
        sizes = [f.bytes for f in by_bpw]
        assert sizes == sorted(sizes), f"{m.id}: sizes not monotonic in bits-per-weight"


def test_params_estimate_reasonable():
    cat = load()
    m = cat.get("qwen3-coder-next")  # params_b is null → derived from file size
    f = m.file("Q4_K_M")
    est = m.params_estimate(f)
    assert 60 < est < 100  # 48.5 GB at ~4.85 bpw → ~80B class


def test_json_is_pretty_and_has_notes():
    data = json.loads(bundled_path().read_text())
    assert data["schema_version"] == 1
    assert any("Hugging Face API" in n for n in data["notes"])
