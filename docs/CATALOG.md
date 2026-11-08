# The model catalog

`datas/catalog/models.json` (bundled) + `~/.local/share/datas/catalog.json` (yours; same
schema; entries with the same `id` override). Browse with `datas catalog list` or
`GET /api/catalog`.

## Curation rules

1. **Verified sizes only.** Every `files[].bytes` is read from the Hugging Face API
   (`/api/models/<repo>/tree/main`) and stamped with `verified: YYYY-MM-DD`. No estimates,
   no "about 4 GB". `datas catalog refresh` re-reads them and reports drift;
   `--write` updates the bundled file.
2. **Official conversions first.** `ggml-org/*-GGUF` (the llama.cpp team) when it exists;
   then the model author's own GGUF (e.g. `Qwen/*-GGUF`); then Unsloth. This guarantees
   the file loads on the pinned llama.cpp build.
3. **Two quants per model as a rule**: a ~4-bit (`Q4_0` / `Q4_K_M` / `MXFP4`) for fit
   and a `Q8_0` for quality when memory allows. Specialist exceptions are documented in
   the entry.
4. **Licenses are stated and flagged.** `license_source: model-card` = checked upstream;
   `unverified` = commonly reported, confirm before relying on it. The UI shows both.
5. **`quality_tier` is curator judgment (1–5)**, used only to rank files that already
   fit. It is not a benchmark score and is revisited each catalog refresh.
6. **`role`** is `general` unless the model is a specialist (`coding`, `vision`,
   `embedding`); specialists never become the default pick unasked.

## Schema

```jsonc
{
  "id": "gemma-4-e4b",                 // stable slug, used in config and CLI
  "name": "Gemma 4 E4B (instruct)",
  "family": "gemma-4", "vendor": "Google",
  "params_b": 8.0,                      // total params in the GGUF (null → derived from size)
  "active_params_b": 4.0,               // per-token active params (MoE / effective)
  "arch": "dense" | "moe",
  "license": "gemma", "license_url": "...", "license_source": "model-card" | "unverified",
  "modalities": ["text","vision"], "capabilities": ["chat","tools","vision", ...],
  "quality_tier": 3, "role": "general", "tags": ["phone-flagship","laptop"],
  "hf_repo": "ggml-org/gemma-4-E4B-it-GGUF",
  "kv": {"layers": 36, "kv_heads": 8, "head_dim": 128},   // optional, only when certain
  "files": [{"quant": "Q4_0", "path": "gemma-4-E4B-it-Q4_0.gguf", "bytes": 4590807392, "verified": "2026-11-08"}],
  "extras": {"mmproj": {"path": "mmproj-….gguf", "bytes": 559874816}}   // vision projector
}
```

Quant names must be keys of `BITS_PER_WEIGHT` in `datas/catalog/__init__.py` (add new
ones there with their nominal bits/weight).

## Current contents (2026-11-08)

| id | params (active) | quants | license | repo |
|---|---|---|---|---|
| qwen3.5-0.8b | 0.8 | Q4_0 0.5G, Q8_0 0.8G | apache-2.0* | ggml-org/Qwen3.5-0.8B-GGUF |
| qwen3-0.6b | 0.6 | Q4_0 0.4G, Q8_0 0.7G | apache-2.0 | ggml-org/Qwen3-0.6B-GGUF |
| gemma-4-e2b | 5 (2) | Q4_0 2.6G, Q8_0 4.6G | gemma | ggml-org/gemma-4-E2B-it-GGUF |
| qwen3-1.7b | 1.7 | Q4_K_M 1.2G, Q8_0 2.0G | apache-2.0 | ggml-org/Qwen3-1.7B-GGUF |
| smollm3-3b | 3 | Q4_K_M 1.8G, Q8_0 3.1G | apache-2.0 | ggml-org/SmolLM3-3B-GGUF |
| qwen3-4b | 4 | Q4_K_M 2.3G, Q8_0 4.0G | apache-2.0 | ggml-org/Qwen3-4B-GGUF |
| gemma-4-e4b | 8 (4) | Q4_0 4.3G, Q8_0 7.5G | gemma | ggml-org/gemma-4-E4B-it-GGUF |
| phi-4-mini | 3.8 | Q4_K_M 2.3G, Q6_K 2.9G, Q8_0 3.8G | mit | unsloth/Phi-4-mini-instruct-GGUF |
| qwen3-8b | 8.2 | Q4_K_M 4.7G, Q6_K 6.3G, Q8_0 8.1G | apache-2.0 | Qwen/Qwen3-8B-GGUF |
| mimo-v2.6-distill-qwen-9b | 9 | Q8_0 8.9G | mit* | ggml-org/MiMo-V2.6-Distill-Qwen-9B-GGUF |
| gemma-4-12b | 12 | Q4_0 6.7G, Q8_0 11.8G | gemma | ggml-org/gemma-4-12B-it-GGUF |
| gpt-oss-20b | 21 (3.6) | MXFP4 11.3G | apache-2.0 | ggml-org/gpt-oss-20b-GGUF |
| qwen3-14b | 14.8 | Q4_K_M 8.4G, Q8_0 14.6G | apache-2.0 | ggml-org/Qwen3-14B-GGUF |
| gemma-4-26b-a4b | 25 (4) | Q4_0 13.6G, Q8_0 25.0G | gemma | ggml-org/gemma-4-26B-A4B-it-GGUF |
| qwen3.8-27b | 27 | Q4_K_M 17.7G, Q8_0 26.6G | apache-2.0* | ggml-org/Qwen3.8-27B-GGUF |
| qwen3.6-35b-a3b | 35 (3) | Q4_K_M 19.0G, Q8_0 34.4G | apache-2.0* | ggml-org/Qwen3.6-35B-A3B-GGUF |
| nemotron-3.5-lightning-30b-a3b | 30 (3) | Q4_0 17.6G, Q8_0 31.3G | nvidia-open-model-license* | ggml-org/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF |
| gemma-4-31b | 31 | Q4_0 16.8G, Q8_0 30.4G | gemma | ggml-org/gemma-4-31B-it-GGUF |
| qwen3-coder-next (role: coding) | ? (MoE) | UD-Q2_K_XL 24.9G, Q4_K_M 45.2G | apache-2.0* | unsloth/Qwen3-Coder-Next-GGUF |
| gpt-oss-120b | 117 (5.1) | MXFP4 59.0G | apache-2.0 | ggml-org/gpt-oss-120b-GGUF |

`*` = `license_source: unverified`. Sizes in GiB, rounded; exact bytes are in the JSON.

### Deliberately left out (for now)

- **Qwen3.8-Flash-Next** (125B MoE) — only sharded/foldered quants; `datas catalog add`
  with the exact shard once we support multi-file entries (see ROADMAP).
- **DeepSeek V4 Flash** (ggml-org/DeepSeek-V4-Flash-0731-GGUF, 160+ GB) — pool-only
  territory; add manually if you have the cluster.
- **Llama 3.x** — superseded on every size by the models above.
- Vision-only, embedding, OCR, TTS and ASR repos — different product surface.

## Adding a model

```bash
# any GGUF on the Hub; size and sha come from the API
datas catalog add unsloth/gemma-4-E4B-it-GGUF gemma-4-E4B-it-UD-Q4_K_XL.gguf --model-id gemma-4-e4b-ud --name "Gemma 4 E4B (Unsloth UD)"
```

Or edit `~/.local/share/datas/catalog.json` by hand (same schema), then
`datas catalog list`. To propose it upstream, add it to `datas/catalog/models.json`, run
`datas catalog refresh` so the `verified` stamps are fresh, run `pytest`, open a PR.

## Refreshing

```bash
datas catalog refresh          # report size drift vs the Hub
datas catalog refresh --write  # update models.json in place
```

Run before each release. If a repo is renamed or a file removed, the refresh prints the
error and you fix the entry.
