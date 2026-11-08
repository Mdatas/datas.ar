"""Deterministic model recommender.

No LLM is involved in choosing a model. The decision is memory arithmetic:

    needed = weights + kv_cache(context) + runtime_overhead
    fits   = needed <= budget(device, headroom policy)

The *headroom policy* is the product's core promise — "run the best AI without freezing
the device" — so it is explicit and user-adjustable: by default we reserve the larger of
25% of RAM or 2 GiB for the OS and your other apps, and 10% (min 512 MiB) of each GPU's
VRAM for the display/driver.

Weights are exact (byte sizes verified against the Hugging Face API, see the catalog).
KV cache is exact when the catalog carries a ``kv`` hint, otherwise a conservative
estimate that is replaced by the real value read from the GGUF header once the file is
on disk (``datas.runtime.gguf_meta``). Runtime overhead is a documented rule of thumb.

Design borrowed from the hardware-sizing CLIs that came before (llmfit, canirunllm,
llm-checker): deterministic math, fit levels, never recommend "too tight".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from datas.catalog import Catalog, CatalogModel, KVHint, ModelFile
from datas.catalog import load as load_catalog
from datas.hardware.detect import DeviceSpec

GiB = 2**30
MiB = 2**20

SPEED_RANK = {"fast": 0, "ok": 1, "slow": 2, "crawl": 3}


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


@dataclass
class Budget:
    ram_total: int
    ram_budget: int  # what we allow the model to use from system RAM
    ram_headroom: int  # what we keep free
    vram_total: int  # dedicated VRAM across GPUs (0 if none / unified)
    vram_budget: int
    unified: bool  # GPU shares RAM (Apple Silicon, iGPU, phone)
    backend: str
    disk_free: int
    threads: int
    nodes: int = 1  # >1 in pool mode

    @property
    def total_budget(self) -> int:
        return self.ram_budget + self.vram_budget

    def to_dict(self) -> dict:
        return {
            "ram_total_gib": round(self.ram_total / GiB, 1),
            "ram_budget_gib": round(self.ram_budget / GiB, 1),
            "ram_headroom_gib": round(self.ram_headroom / GiB, 1),
            "vram_total_gib": round(self.vram_total / GiB, 1),
            "vram_budget_gib": round(self.vram_budget / GiB, 1),
            "total_budget_gib": round(self.total_budget / GiB, 1),
            "unified": self.unified,
            "backend": self.backend,
            "disk_free_gib": round(self.disk_free / GiB, 1),
            "threads": self.threads,
            "nodes": self.nodes,
        }


DEFAULT_HEADROOM = {"phone": 0.40, "laptop": 0.25, "desktop": 0.25, "server": 0.15}


def default_headroom(spec: DeviceSpec) -> float:
    """Phones get more headroom: Android/iOS kill memory-hungry apps without warning."""
    return DEFAULT_HEADROOM.get(spec.form_factor, 0.25)


def budget_for(
    spec: DeviceSpec, headroom: float | None = None, headroom_min_gib: float = 2.0
) -> Budget:
    if headroom is None:
        headroom = default_headroom(spec)
    ram_headroom = int(max(headroom_min_gib * GiB, headroom * spec.ram_total))
    ram_budget = max(0, spec.ram_total - ram_headroom)
    gpu = spec.best_gpu
    unified = bool(gpu and gpu.unified)
    vram_total = spec.dedicated_vram_total
    vram_budget = 0
    if vram_total:
        # keep 10% (min 512 MiB) of VRAM for the display/driver
        vram_budget = sum(
            max(0, (g.vram_total or 0) - max(512 * MiB, int(0.10 * (g.vram_total or 0))))
            for g in spec.gpus
            if g.vram_total and not g.unified
        )
    if unified:
        # Apple Silicon lets the GPU address roughly 75% of RAM by default (the kernel's
        # recommended max working set). Our RAM headroom already keeps us under that.
        pass
    # Threads: physical cores, leaving one free on 4+ core machines so the UI stays responsive.
    threads = spec.cpu_cores_physical
    if threads >= 4:
        threads -= 1
    return Budget(
        ram_total=spec.ram_total,
        ram_budget=ram_budget,
        ram_headroom=ram_headroom,
        vram_total=vram_total,
        vram_budget=vram_budget,
        unified=unified,
        backend=spec.suggested_backend,
        disk_free=spec.disk_free_models,
        threads=max(1, threads),
    )


def pool_budget(budgets: list[Budget]) -> Budget:
    """Sum per-node budgets for llama.cpp RPC mode (memory is additive, speed is not)."""
    if not budgets:
        raise ValueError("pool needs at least one node")
    head = budgets[0]
    return Budget(
        ram_total=sum(b.ram_total for b in budgets),
        ram_budget=sum(b.ram_budget for b in budgets),
        ram_headroom=sum(b.ram_headroom for b in budgets),
        vram_total=sum(b.vram_total for b in budgets),
        vram_budget=sum(b.vram_budget for b in budgets),
        unified=all(b.unified for b in budgets),
        backend=head.backend,
        disk_free=head.disk_free,  # the head node holds the file
        threads=head.threads,
        nodes=len(budgets),
    )


# ---------------------------------------------------------------------------
# Memory model
# ---------------------------------------------------------------------------


def _estimate_layers(params_b: float) -> int:
    """Conservative layer count by size class (used only when the catalog has no kv hint).

    Published configs of common open models: ~28 layers at ≤2B, 36 at 3-9B, 40-48 at
    12-15B, 60-64 at 27-35B, ~80 at 70-80B. We round up so the KV estimate errs high.
    """
    if params_b <= 2:
        return 28
    if params_b <= 9:
        return 36
    if params_b <= 15:
        return 48
    if params_b <= 35:
        return 64
    if params_b <= 80:
        return 80
    return 96


def kv_hint_for(model: CatalogModel, f: ModelFile) -> tuple[KVHint, bool]:
    """Return (hint, is_exact)."""
    if model.kv:
        return model.kv, True
    params = model.params_estimate(f)
    return KVHint(layers=_estimate_layers(params), kv_heads=8, head_dim=128), False


def runtime_overhead(weights: int) -> int:
    """Compute buffers, tokenizer, program and allocator slack. Rule of thumb, errs high."""
    return int(0.08 * weights) + 512 * MiB


@dataclass
class MemoryNeed:
    weights: int
    kv_cache: int
    overhead: int
    kv_exact: bool
    context: int
    kv_bits: int

    @property
    def total(self) -> int:
        return self.weights + self.kv_cache + self.overhead


def memory_need(
    model: CatalogModel, f: ModelFile, context: int, kv_bits: int = 16, with_vision: bool = False
) -> MemoryNeed:
    hint, exact = kv_hint_for(model, f)
    weights = f.bytes
    if with_vision and "mmproj" in model.extras:
        weights += model.extras["mmproj"].bytes
    kv = hint.bytes_per_token(kv_bits) * context
    return MemoryNeed(weights, kv, runtime_overhead(weights), exact, context, kv_bits)


# ---------------------------------------------------------------------------
# Candidate evaluation
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    model_id: str
    name: str
    quant: str
    path: str
    hf_repo: str
    quality_tier: int
    capabilities: list[str]
    need: MemoryNeed
    fits: bool
    placement: str  # gpu | split | cpu | unified | pool | none
    ngl: int  # layers to offload (99 = all)
    gpu_fraction: float
    speed_class: str  # fast | ok | slow | crawl
    margin: int  # budget - need (negative when it doesn't fit)
    disk_ok: bool
    fit_level: str = "none"  # comfortable | tight | none
    role: str = "general"
    effective_tier: int = 3  # quality_tier minus a penalty for very low-bit quants
    active_bytes: int = 0  # bytes touched per generated token — what sets tokens/s
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fallbacks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "quant": self.quant,
            "path": self.path,
            "hf_repo": self.hf_repo,
            "quality_tier": self.quality_tier,
            "effective_tier": self.effective_tier,
            "role": self.role,
            "fit_level": self.fit_level,
            "capabilities": self.capabilities,
            "weights_gib": round(self.need.weights / GiB, 2),
            "kv_cache_gib": round(self.need.kv_cache / GiB, 2),
            "overhead_gib": round(self.need.overhead / GiB, 2),
            "needed_gib": round(self.need.total / GiB, 2),
            "kv_exact": self.need.kv_exact,
            "context": self.need.context,
            "kv_bits": self.need.kv_bits,
            "fits": self.fits,
            "placement": self.placement,
            "ngl": self.ngl,
            "gpu_fraction": round(self.gpu_fraction, 2),
            "speed_class": self.speed_class,
            "margin_gib": round(self.margin / GiB, 2),
            "disk_ok": self.disk_ok,
            "active_gib_per_token": round(self.active_bytes / GiB, 2),
            "reasons": self.reasons,
            "warnings": self.warnings,
            "fallbacks": self.fallbacks,
        }


def _speed_class(placement: str, gpu_fraction: float, active_bytes: int, backend: str) -> str:
    """Speed class from the bytes touched per token and where they live.

    Generation speed is bandwidth-bound: tokens/s ≈ memory bandwidth / active bytes per
    token. Dedicated GPUs move hundreds of GB/s to >1 TB/s; Apple unified memory 100–800
    GB/s; DDR4/DDR5 system RAM 20–90 GB/s; a phone 30–70 GB/s. The thresholds below are
    chosen so "ok" means roughly ≥5 tokens/s on typical hardware of that class — a
    readable chat pace — and "fast" means comfortably more. They are classes, not
    measurements: run `datas bench` after install for the real number.
    """
    a = active_bytes / GiB
    if placement == "gpu":
        return "fast" if a <= 20 else "ok"
    if placement == "unified":
        if backend == "metal":
            return "fast" if a <= 20 else "ok"
        return "ok" if a <= 3.5 else ("slow" if a <= 7 else "crawl")  # iGPU / phone: DDR-class
    if placement == "split":
        # the CPU-resident part dominates: scale by what stays in RAM
        cpu_part = a * (1 - gpu_fraction)
        if cpu_part <= 1.5:
            return "fast" if a <= 20 else "ok"
        if cpu_part <= 4:
            return "ok"
        return "slow" if cpu_part <= 8 else "crawl"
    if placement == "cpu":
        if a <= 5:
            return "ok"
        if a <= 10:
            return "slow"
        return "crawl"
    if placement == "pool":
        # Wi-Fi/Ethernet round trips per token: fine for small-active MoE, painful for dense
        return "ok" if a <= 5 else ("slow" if a <= 12 else "crawl")
    return "crawl"


def comfortable_margin(budget_bytes: int) -> int:
    """Never recommend 'too tight': keep ≥10% of the budget (min 512 MiB) unallocated."""
    return max(512 * MiB, int(0.10 * budget_bytes))


def evaluate(
    model: CatalogModel,
    f: ModelFile,
    budget: Budget,
    context: int,
    kv_bits: int = 16,
    pool: bool = False,
) -> Candidate:
    need = memory_need(model, f, context, kv_bits)
    hint, _ = kv_hint_for(model, f)
    active_b = model.active_estimate(f)
    total_b = model.params_estimate(f)
    active_bytes = int(need.weights * (active_b / total_b)) if total_b else need.weights

    reasons: list[str] = []
    warnings: list[str] = []
    fallbacks: list[str] = []
    disk_ok = f.bytes + 1 * GiB <= budget.disk_free
    if not disk_ok:
        warnings.append(
            f"Needs {f.bytes / GiB:.1f} GiB of disk; only {budget.disk_free / GiB:.1f} GiB free."
        )
    if not need.kv_exact:
        warnings.append(
            "KV-cache size is an estimate until the GGUF header is read after download."
        )

    placement, ngl, frac, fits = "none", 0, 0.0, False
    if pool:
        fits = need.total <= budget.total_budget
        placement = "pool" if fits else "none"
        ngl, frac = 99, 1.0
        if fits:
            reasons.append(
                f"Fits across {budget.nodes} nodes ({budget.total_budget / GiB:.1f} GiB pooled)."
            )
    elif budget.unified:
        fits = need.total <= budget.ram_budget
        if fits:
            placement, ngl, frac = "unified", 99, 1.0
            reasons.append(
                f"Fits in unified memory ({need.total / GiB:.1f} of {budget.ram_budget / GiB:.1f} GiB budget)."
            )
    else:
        if budget.vram_budget and need.total <= budget.vram_budget:
            fits, placement, ngl, frac = True, "gpu", 99, 1.0
            reasons.append(
                f"Fits entirely in VRAM ({need.total / GiB:.1f} of {budget.vram_budget / GiB:.1f} GiB)."
            )
        elif budget.vram_budget and need.total <= budget.vram_budget + budget.ram_budget:
            fits, placement = True, "split"
            frac = budget.vram_budget / need.total
            ngl = max(1, min(hint.layers - 1, math.floor(hint.layers * frac)))
            reasons.append(f"Splits: ~{frac:.0%} on GPU ({ngl}/{hint.layers} layers), rest in RAM.")
        elif need.total <= budget.ram_budget:
            fits, placement, ngl, frac = True, "cpu", 0, 0.0
            reasons.append(
                f"Fits in RAM ({need.total / GiB:.1f} of {budget.ram_budget / GiB:.1f} GiB budget), CPU inference."
            )

    if placement == "gpu":
        pool_budget_bytes = budget.vram_budget
    elif placement in ("split", "pool") or (not fits and not budget.unified):
        pool_budget_bytes = budget.total_budget
    else:
        pool_budget_bytes = budget.ram_budget
    margin = pool_budget_bytes - need.total
    speed = _speed_class(placement, frac, active_bytes, budget.backend) if fits else "crawl"
    fit_level = "none"
    if fits:
        fit_level = "comfortable" if margin >= comfortable_margin(pool_budget_bytes) else "tight"
        if fit_level == "tight":
            warnings.append(
                f"Tight fit: only {margin / GiB:.1f} GiB spare inside the budget. Works, but close other heavy apps first."
            )

    # Very low-bit quants lose noticeable quality: rank them a tier lower.
    from datas.catalog import BITS_PER_WEIGHT

    bpw = BITS_PER_WEIGHT.get(f.quant.upper(), 4.85)
    effective_tier = model.quality_tier - (1 if bpw < 3.6 else 0)

    if not fits:
        gap = need.total - (budget.total_budget if not budget.unified else budget.ram_budget)
        reasons.append(
            f"Needs {need.total / GiB:.1f} GiB; budget is {(budget.total_budget if not budget.unified else budget.ram_budget) / GiB:.1f} GiB (short by {gap / GiB:.1f} GiB)."
        )
        if kv_bits == 16:
            fallbacks.append("Use an 8-bit KV cache (--kv 8) to halve the context memory.")
        if context > 4096:
            fallbacks.append(f"Lower the context from {context} to 4096.")
        fallbacks.append("Lower the headroom slider (keeps less RAM free for other apps).")
        smaller = [x for x in model.files if x.bytes < f.bytes]
        if smaller:
            fallbacks.append(f"Try the smaller quant: {max(smaller, key=lambda x: x.bytes).quant}.")
    else:
        if model.arch == "moe":
            reasons.append(
                f"MoE: only ~{active_b:.1f}B of {total_b:.0f}B parameters are active per token, so it runs faster than its size suggests."
            )
        if speed in ("slow", "crawl"):
            warnings.append(
                "Expect slow generation on this placement; a smaller model will feel much snappier."
            )

    return Candidate(
        model_id=model.id,
        name=model.name,
        quant=f.quant,
        path=f.path,
        hf_repo=model.hf_repo,
        quality_tier=model.quality_tier,
        capabilities=model.capabilities,
        need=need,
        fits=fits,
        placement=placement,
        ngl=ngl,
        gpu_fraction=frac,
        speed_class=speed,
        margin=margin,
        disk_ok=disk_ok,
        fit_level=fit_level,
        role=model.role,
        effective_tier=effective_tier,
        active_bytes=active_bytes,
        reasons=reasons,
        warnings=warnings,
        fallbacks=fallbacks,
    )


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


@dataclass
class Recommendation:
    budget: Budget
    context: int
    kv_bits: int
    default: Candidate | None
    fits: list[Candidate]
    does_not_fit: list[Candidate]

    def to_dict(self) -> dict:
        return {
            "budget": self.budget.to_dict(),
            "context": self.context,
            "kv_bits": self.kv_bits,
            "default": self.default.to_dict() if self.default else None,
            "fits": [c.to_dict() for c in self.fits],
            "does_not_fit": [c.to_dict() for c in self.does_not_fit],
        }


PLACEMENT_RANK = {"gpu": 0, "unified": 0, "split": 1, "cpu": 2, "pool": 2, "none": 3}


def _usable(c: Candidate) -> bool:
    return c.speed_class in ("fast", "ok")


def _rank_key(c: Candidate) -> tuple:
    # Usable speed first; then quality (after the low-bit penalty); then speed; then
    # comfortable over tight; then simpler placement; then the larger quant.
    return (
        0 if _usable(c) else 1,
        -c.effective_tier,
        SPEED_RANK[c.speed_class],
        0 if c.fit_level == "comfortable" else 1,
        PLACEMENT_RANK[c.placement],
        -c.need.weights,
    )


def recommend(
    spec: DeviceSpec | None = None,
    catalog: Catalog | None = None,
    *,
    headroom: float | None = None,
    headroom_min_gib: float = 2.0,
    context: int = 8192,
    kv_bits: int = 16,
    want: list[str] | None = None,
    budget: Budget | None = None,
    pool: bool = False,
    role: str = "general",
) -> Recommendation:
    """Rank every catalog file against the device budget and pick a default.

    ``want`` filters by capability (e.g. ["coding"], ["vision"]).
    ``role`` selects which specialists may become the default ("general" excludes them).
    ``budget`` lets pool mode pass a summed budget.
    """
    catalog = catalog or load_catalog()
    if budget is None:
        if spec is None:
            from datas.hardware.detect import detect

            spec = detect()
        budget = budget_for(spec, headroom, headroom_min_gib)

    cands: list[Candidate] = []
    for m in catalog.models:
        if want and not all(w in m.capabilities for w in want):
            continue
        for f in m.files:
            cands.append(evaluate(m, f, budget, context, kv_bits, pool=pool))

    fits = sorted([c for c in cands if c.fits and c.disk_ok], key=_rank_key)
    nofit = sorted([c for c in cands if not (c.fits and c.disk_ok)], key=lambda c: c.need.total)

    # Default: best quality among comfortable, usable candidates of the requested role.
    # Specialists (role != general) are only eligible when asked for, and then come first.
    specialists = [c for c in fits if role != "general" and c.role == role]
    generals = [c for c in fits if c.role == "general"]
    pools = [specialists, generals] if role != "general" else [generals]
    pick: Candidate | None = None
    for group in pools:
        comfortable = [c for c in group if c.fit_level == "comfortable" and _usable(c)]
        usable = [c for c in group if _usable(c)]
        chosen = (comfortable or usable or group or [None])[0]
        if chosen is not None:
            pick = chosen
            break
    if pick is None and fits:
        pick = fits[0]
    if pick:
        # Within the chosen model: prefer the simplest placement (all on GPU beats a split),
        # then quality (a Q2 is not worth a speed class), then speed, then more of the
        # model on the GPU, then the largest quant that is still comfortable.
        same = [c for c in fits if c.model_id == pick.model_id]
        good = [c for c in same if c.fit_level == "comfortable" and _usable(c)] or same
        good.sort(
            key=lambda c: (
                PLACEMENT_RANK[c.placement],
                -c.effective_tier,
                SPEED_RANK[c.speed_class],
                -round(c.gpu_fraction, 1),
                -c.need.weights,
            )
        )
        pick = good[0]

    # Collapse to one entry per model in the visible lists (best quant each), keep order.
    seen: set[str] = set()
    fits_dedup: list[Candidate] = []
    for c in fits:
        if c.model_id not in seen:
            seen.add(c.model_id)
            fits_dedup.append(c)
    seen = set()
    nofit_dedup: list[Candidate] = []
    for c in nofit:
        if c.model_id not in seen and c.model_id not in {x.model_id for x in fits_dedup}:
            seen.add(c.model_id)
            nofit_dedup.append(c)

    return Recommendation(budget, context, kv_bits, pick, fits_dedup, nofit_dedup)


def llama_server_args(
    c: Candidate,
    budget: Budget,
    model_path: str,
    port: int,
    host: str = "127.0.0.1",
    rpc: list[str] | None = None,
    mmproj_path: str | None = None,
    exact_layers: bool = False,
) -> list[str]:
    """Translate a candidate into llama-server flags.

    Two layers of protection keep the device responsive:
    1. We chose a model whose *estimated* need fits our budget (this module).
    2. llama-server's own ``--fit`` (default on in current builds) adjusts the GPU layer
       split to the device's real free memory, with ``--fit-target`` = our RAM headroom
       as the margin it must leave untouched. ``-ngl auto`` lets it place layers exactly;
       ``exact_layers`` forces our computed ``ngl`` instead (older builds / debugging).
    """
    args = [
        "-m",
        model_path,
        "--host",
        host,
        "--port",
        str(port),
        "-c",
        str(c.need.context),
        "-t",
        str(budget.threads),
        "--jinja",  # model's own chat template → correct tool-calling format
        "-fa",
        "auto",
        "--fit",
        "on",
        "--fit-target",
        str(max(256, budget.ram_headroom // MiB)),
    ]
    if exact_layers or c.placement == "cpu":
        args += ["-ngl", str(c.ngl if c.placement != "cpu" else 0)]
    else:
        args += ["-ngl", "auto"]
    if c.need.kv_bits == 8:
        args += ["-ctk", "q8_0", "-ctv", "q8_0"]
    if rpc:
        args += ["--rpc", ",".join(rpc)]
    if mmproj_path:
        args += ["--mmproj", mmproj_path]
    return args
