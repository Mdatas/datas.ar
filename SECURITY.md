# Security

## Threat model in one paragraph

Datas runs on your device and binds to `127.0.0.1`. It downloads two kinds of things:
llama.cpp release archives from GitHub (`ggml-org/llama.cpp`, pinned by tag) and model
files from Hugging Face (verified against the Hub's SHA-256; a mismatch deletes the
file). API keys you add are stored in the local config file and sent only to the base URL
you configured. There is no telemetry, no account, no auto-update that runs code.

## Things to know

- `datas serve --host 0.0.0.0` exposes the UI and the `/v1` proxy — and therefore your
  remote API keys' spending — to the network. Use a VPN or an authenticating reverse proxy.
- `datas pool worker` runs `ggml-rpc-server`, which has **no authentication or
  encryption**. LAN/VPN only.
- The agent's `run_command` tool is off unless you pass `--allow-shell`, and then asks
  before each command unless `--yes`. Files are confined to the workspace directory.
- Model weights are data, but a malicious GGUF could exploit a parser bug in llama.cpp.
  Stick to the curated catalog or repos you trust; `datas runtime update` tracks upstream
  fixes.
- Release archives are fetched over HTTPS from GitHub; we do not yet verify a signature
  (upstream does not publish one). Pinning by tag + the integrity of HTTPS is the current
  guarantee. Sigstore verification is on the roadmap when upstream offers it.

## Reporting

Open a GitHub issue marked *security* or contact the maintainer privately through the
address on the GitHub profile. Please include your OS, Datas version
(`datas --version`) and `datas doctor` output with keys redacted.
