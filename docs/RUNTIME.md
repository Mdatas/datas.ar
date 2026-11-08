# Runtime: llama.cpp

Datas does not build or bundle an inference engine. It downloads the prebuilt
[llama.cpp](https://github.com/ggml-org/llama.cpp) release for your platform the first
time you install a model, and pins the build tag.

## Why llama.cpp

- One engine and one file format (GGUF) across Linux, macOS, Windows, Android, iOS.
- CPU, CUDA, ROCm, Metal, Vulkan, OpenCL (Adreno), SYCL and OpenVINO backends.
- `llama-server`: OpenAI-compatible HTTP API, tool calling via the model's own chat
  template (`--jinja`), vision via `--mmproj`, speculative decoding, multimodal.
- `ggml-rpc-server` + `--rpc`: distributed inference across machines.
- `llama-bench`: real tokens/s numbers.
- `--fit on`: the engine itself sizes the layer split to free memory, with a margin we set.
- MIT licensed, 100k+ stars, the de-facto core of nearly every local-AI app.

## Asset selection

Release assets follow `llama-<tag>-bin-<platform>[-<backend>[-<version>]]-<arch>.{tar.gz,zip}`
(see `datas/runtime/llamacpp.py::asset_patterns`). Preference order per device:

| Device | Tries, in order |
|---|---|
| Linux x64 + NVIDIA | `ubuntu-cuda-<driver major>.x-x64` → `ubuntu-cuda-12.x` → `ubuntu-vulkan-x64` → `ubuntu-x64` |
| Linux x64 + AMD dGPU | `ubuntu-rocm-*` → `ubuntu-vulkan-x64` → `ubuntu-x64` |
| Linux + iGPU/other | `ubuntu-vulkan-<arch>` → `ubuntu-<arch>` |
| Linux, no GPU | `ubuntu-<arch>` |
| macOS | `macos-arm64` / `macos-x64` (Metal built in) |
| Windows x64 + NVIDIA | `win-cuda-<major>.x-x64.zip` + `cudart-llama-bin-win-cuda-….zip` → `win-vulkan-x64` → `win-cpu-x64` |
| Windows x64 + AMD | `win-rocm-*` → `win-vulkan-x64` → `win-cpu-x64` |
| Windows arm64 + Adreno | `win-opencl-adreno-arm64` → `win-vulkan-arm64` → `win-cpu-arm64` |
| Android arm64 | `android-arm64-snapdragon` (Qualcomm SoC) → `android-arm64` |

CUDA builds also fetch their `cudart-*` runtime pack so no CUDA toolkit install is
needed — only the NVIDIA driver. The CUDA major version is read from `nvidia-smi`.

Override the backend with `datas` config `backend` (`cpu`, `cuda`, `rocm`, `vulkan`,
`metal`) or `POST /api/settings {"backend": "vulkan"}` — useful when a driver is flaky.

## Resolving the release

1. **Pinned tag** (`config.llamacpp_tag`, default `KNOWN_GOOD_TAG` = `b11669`, the build
   this Datas release was tested with).
2. GitHub API `releases/tags/<tag>` → exact asset list → pattern match.
3. If the API is unavailable (rate limit, firewall): HEAD-probe constructed asset URLs for
   that tag (`_probe_names`), trying known CUDA/ROCm version suffixes. This path is what
   the build machine used for the tests in this repo.

`datas runtime update` asks the API (or the Atom feed) for the newest `bNNNN` build,
re-pins and installs. `datas runtime pin <tag>` pins explicitly. **Pool nodes must share
a tag** — the RPC protocol changes between builds.

## Layout on disk

```
~/.local/share/datas/llamacpp/
  downloads/llama-b11669-bin-ubuntu-x64.tar.gz
  b11669/
    .datas-ok                       # tag · asset · backend
    llama-b11669/                   # as extracted (flat on Linux/macOS; flat on Windows)
      llama-server, ggml-rpc-server, llama-bench, llama-cli, lib*.so …
```

`find_binary()` searches recursively, so layout changes upstream don't break us. The RPC
worker is accepted under both names (`rpc-server`, `ggml-rpc-server`).

## Flags we pass to llama-server

```
-m <gguf> --host 127.0.0.1 --port 8421
-c <context>             # from the recommender (capped at the model's trained length)
-t <threads>             # physical cores, minus one on 4+ core machines
--jinja                  # model's chat template → correct tool-call format
-fa auto                 # flash attention when the backend supports it
--fit on --fit-target <ram_headroom MiB>   # engine-side fit with our margin
-ngl auto | 0            # auto unless CPU placement
[-ctk q8_0 -ctv q8_0]    # 8-bit KV when chosen
[--rpc host:port,…]      # pool mode
[--mmproj <file>]        # vision
```

Not passed on purpose: `--api-key` (local only), `--mlock` (would fight the headroom),
`--no-mmap` (mmap keeps RSS honest).

## Logs & diagnosis

`~/.local/share/datas/logs/llama-server.log`; `datas doctor` prints the tail;
`GET /api/logs`. A server that exits within the health-check window raises with the last
40 log lines so the UI shows the real reason (usually "out of memory" or a missing driver).

## Benchmarks

`datas bench` / UI *Benchmark* runs `llama-bench -m <model> -p 128 -n 64 -ngl … -o json`
after stopping the server (so the measurement isn't competing for memory). Reports prompt
and generation tokens/s.
