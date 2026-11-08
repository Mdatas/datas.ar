# The recommender

`datas/recommend/engine.py`. No model is consulted. Everything below is arithmetic you can
check with `datas recommend --json`.

## 1. Budget — how much the model may use

```
ram_headroom = max(headroom_min_gib · GiB, headroom · ram_total)
ram_budget   = ram_total − ram_headroom
vram_budget  = Σ over dedicated GPUs: vram_total − max(512 MiB, 10 % · vram_total)
total_budget = ram_budget + vram_budget
```

Defaults: `headroom_min_gib = 2`, `headroom = 0.25` (desktop/laptop), `0.40` (phone),
`0.15` (server). The UI slider changes `headroom`; it is saved in config.

- **Unified memory** (Apple Silicon, iGPUs, phones): there is no separate VRAM; the
  model lives in `ram_budget`. macOS caps the GPU's working set at roughly 75 % of RAM by
  default; our 25 % headroom keeps us under it.
- **Threads**: physical cores, minus one on 4+ core machines, so the UI and the rest of
  the system keep a core.

## 2. Need — how much a (model, file) takes

```
weights  = file.bytes                                   # exact (Hugging Face API)
kv_cache = 2 · layers · kv_heads · head_dim · (bits/8) · context
overhead = 8 % · weights + 512 MiB                      # compute buffers, program, slack
need     = weights + kv_cache + overhead
```

`layers / kv_heads / head_dim` come from the catalog's `kv` hint when present (Qwen3,
Phi-4 mini, SmolLM3, gpt-oss-20b). Otherwise a **conservative estimate** by size class is
used (28 layers ≤2B, 36 ≤9B, 48 ≤15B, 64 ≤35B, 80 ≤80B, 96 above; 8 KV heads × 128 dims)
and the candidate is flagged `kv_exact: false`. After download, the GGUF header gives the
real values and `orchestrator.refine()` recomputes; if the exact need no longer fits, the
context is halved (down to 2048) and the user is told.

8-bit KV cache (`--kv 8` / UI toggle) halves `kv_cache` via `-ctk q8_0 -ctv q8_0`.

## 3. Placement

Evaluated in this order, first match wins:

| Placement | Condition | llama-server |
|---|---|---|
| `gpu` | `need ≤ vram_budget` | `-ngl auto` (all layers) |
| `split` | `need ≤ vram_budget + ram_budget` | `-ngl auto` (llama.cpp fits exactly; we show `floor(layers · vram_budget/need)`) |
| `cpu` | `need ≤ ram_budget`, no dedicated GPU | `-ngl 0` |
| `unified` | unified-memory device, `need ≤ ram_budget` | `-ngl auto` |
| `pool` | pool mode, `need ≤ Σ budgets` | `--rpc host:port,…` |
| `none` | nothing above | — (listed under "doesn't fit" with hints) |

## 4. Fit level

```
margin      = budget_used_for_placement − need
comfortable = margin ≥ max(512 MiB, 10 % of that budget)
tight       = 0 ≤ margin < that
```

`tight` candidates are shown and runnable but are never the default (borrowed from
llmfit's "TooTight is never recommended").

## 5. Speed class

Generation is bandwidth-bound: tokens/s ≈ memory bandwidth ÷ bytes touched per token.

```
active_bytes = weights · (active_params / total_params)     # MoE touches a fraction
```

| Placement | fast | ok | slow | crawl |
|---|---|---|---|---|
| gpu / metal-unified | ≤ 20 GiB active | > 20 | | |
| split (by the part left in RAM = active·(1−gpu_fraction)) | ≤ 1.5 GiB | ≤ 4 | ≤ 8 | > 8 |
| cpu | — | ≤ 5 GiB | ≤ 10 | > 10 |
| iGPU/phone unified | — | ≤ 3.5 GiB | ≤ 7 | > 7 |
| pool | — | ≤ 5 GiB | ≤ 12 | > 12 |

"ok" is meant to be ≈ 5+ tokens/s on typical hardware of that class — readable chat.
These are classes, not predictions; `datas bench` / the Benchmark button measures the
real number with `llama-bench`.

## 6. Ranking and the default pick

Every file that fits is sorted by:

1. usable (`fast`/`ok`) before `slow`/`crawl`
2. `effective_tier` (catalog `quality_tier`, minus 1 for quants under ~3.6 bits/weight)
3. speed class
4. comfortable before tight
5. simpler placement (gpu/unified → split → cpu/pool)
6. larger file

The default is the first **comfortable, usable** candidate whose `role` is `general`
(specialists like `qwen3-coder-next` are only eligible when you ask for `--role coding`,
and then they come first). Within the chosen model, the file is picked by: placement →
effective tier → speed → more of the model on the GPU → larger quant.

## 7. Second safety net at launch

```
llama-server … --fit on --fit-target <ram_headroom in MiB> -ngl auto -fa auto --jinja
```

llama.cpp's own fitter then places layers against the *real* free memory at that moment,
leaving at least our headroom untouched. So even if an estimate is off, the device keeps
its margin. (Verified against llama.cpp b11669 `--help`.)

## 8. Worked example

8 GiB laptop, no GPU, 25 % headroom → budget 6.0 GiB, comfortable margin 0.6 GiB.

| model | quant | weights | KV @8k | overhead | need | result |
|---|---|---|---|---|---|---|
| Phi-4 mini | Q6_K | 2.94 | 1.00 (exact) | 0.74 | 4.67 | cpu · ok · comfortable → **default** |
| Qwen3 4B | Q4_K_M | 2.33 | 1.13 (exact) | 0.70 | 4.14 | cpu · ok · comfortable |
| Gemma 4 E4B | Q4_0 | 4.28 | 1.13 (est.) | 0.84 | 6.24 | doesn't fit → "use 8-bit KV / lower ctx" |

Run `datas recommend --context 4096` on the same machine and Gemma 4 E4B fits (tight).

## Known limits

- Overhead is a rule of thumb. llama.cpp's compute buffers scale with batch size and
  context; `--fit` covers the difference at launch.
- Speed classes ignore CPU ISA quality (AVX-512 vs plain AVX2) and memory channel count.
  Benchmarks exist for exactly that reason.
- MoE models whose activation ratio is unknown are assumed to activate 1/8 of their
  parameters.
