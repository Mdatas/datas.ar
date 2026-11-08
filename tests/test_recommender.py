from datas.catalog import load
from datas.recommend.engine import (
    GiB,
    budget_for,
    comfortable_margin,
    default_headroom,
    evaluate,
    llama_server_args,
    memory_need,
    pool_budget,
    recommend,
)


def test_budget_headroom_rules(vm8, phone8, rtx4090_64):
    b = budget_for(vm8)
    assert b.ram_headroom == 2 * GiB  # max(2 GiB, 25% of 8 GiB) = 2 GiB
    assert b.ram_budget == 6 * GiB
    assert b.threads == 2  # 2 cores: keep both
    bp = budget_for(phone8)
    assert default_headroom(phone8) == 0.40
    assert bp.ram_headroom == int(0.40 * 8 * GiB)
    bg = budget_for(rtx4090_64)
    assert bg.vram_budget == 24 * GiB - int(0.10 * 24 * GiB)
    assert bg.threads == 15  # leave one core free on big machines


def test_memory_need_uses_exact_kv_when_hinted():
    cat = load()
    m = cat.get("qwen3-4b")  # has kv hint: 36 layers, 8 kv heads, 128 dim
    f = m.file("Q4_K_M")
    need = memory_need(m, f, context=8192, kv_bits=16)
    assert need.kv_exact
    assert need.kv_cache == 2 * 36 * 8 * 128 * 2 * 8192
    need8 = memory_need(m, f, context=8192, kv_bits=8)
    assert need8.kv_cache == need.kv_cache // 2


def test_kv_estimate_flagged_when_unknown():
    cat = load()
    m = cat.get("gemma-4-e4b")
    need = memory_need(m, m.file("Q4_0"), 8192)
    assert not need.kv_exact


def test_default_pick_per_device(vm8, rtx4090_64, mac36, phone8, laptop16_8):
    r = recommend(vm8)
    assert r.default and r.default.fits and r.default.fit_level == "comfortable"
    assert r.default.placement == "cpu"
    assert r.default.speed_class in ("fast", "ok")

    r = recommend(rtx4090_64)
    assert r.default.quality_tier == 5
    assert r.default.role == "general"
    assert r.default.placement in ("gpu", "split")

    r = recommend(mac36)
    assert r.default.placement == "unified" and r.default.speed_class == "fast"

    r = recommend(phone8, context=4096)
    assert r.default.need.total <= budget_for(phone8).ram_budget
    assert r.default.fit_level == "comfortable"

    r = recommend(laptop16_8)
    assert r.default.fits


def test_specialists_never_default_unless_asked(rtx4090_64):
    general = recommend(rtx4090_64)
    assert general.default.model_id != "qwen3-coder-next"
    coding = recommend(rtx4090_64, role="coding", want=["coding"])
    assert coding.default.model_id == "qwen3-coder-next"
    assert coding.default.quant == "Q4_K_M"  # quality beats the Q2 speed bump


def test_low_bit_quant_penalised():
    cat = load()
    m = cat.get("qwen3-coder-next")
    from tests.conftest import spec

    b = budget_for(spec(ram=128, cores=32))
    q2 = evaluate(m, m.file("UD-Q2_K_XL"), b, 8192)
    q4 = evaluate(m, m.file("Q4_K_M"), b, 8192)
    assert q2.effective_tier == q4.effective_tier - 1


def test_does_not_fit_has_fallbacks(vm8):
    r = recommend(vm8)
    assert r.does_not_fit
    c = r.does_not_fit[0]
    assert not c.fits and c.fallbacks and c.margin < 0


def test_comfortable_margin_rule():
    assert comfortable_margin(4 * GiB) == 512 * 2**20
    assert comfortable_margin(64 * GiB) == int(6.4 * GiB)


def test_pool_budget_sums_memory(vm8):
    b = budget_for(vm8)
    p = pool_budget([b, b, b])
    assert p.ram_budget == 3 * b.ram_budget and p.nodes == 3
    r = recommend(vm8, budget=p, pool=True)
    assert r.default.placement == "pool"
    assert r.default.need.total > b.ram_budget  # pooling unlocked a bigger model


def test_llama_args_carry_headroom(vm8):
    r = recommend(vm8)
    args = llama_server_args(r.default, r.budget, "/m.gguf", 8421)
    assert "--fit" in args and args[args.index("--fit-target") + 1] == str(2048)
    assert args[args.index("-ngl") + 1] == "0"  # CPU placement → no offload
    assert "--jinja" in args


def test_kv8_and_context_change_fit(vm8):
    r16 = recommend(vm8, context=16384, kv_bits=16)
    r8 = recommend(vm8, context=16384, kv_bits=8)
    assert len(r8.fits) >= len(r16.fits)
