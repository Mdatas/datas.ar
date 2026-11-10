# Pooling devices by hand (expert)

> **Most people should use *Devices* instead** — see [DEVICES.md](DEVICES.md). Linking your
> devices there gives the same result (their memory adds up so a bigger AI fits) with one
> code, and wraps everything in an encrypted link. In the window: *Devices* → link, then
> *Add an AI → More options → Count the memory of my linked devices*.
>
> This page describes the older, manual way underneath it. It is **unencrypted and has no
> password**, so it is only for a network you fully control or for your own tunnel.

Run one AI across several machines so their memory adds up. Built on llama.cpp's RPC
(Remote Procedure Call) backend; Datas adds the memory arithmetic and the one-command start.

## Quick start

```bash
# every extra device (laptop, old PC, Mac mini …)
pipx install datas-ar
datas pool worker --host 0.0.0.0   # starts llama.cpp's worker (ggml-rpc-server) on port 50052

# the device you chat from: name the workers, then choose the AI yourself
datas pool nodes --set 192.168.1.20:50052,192.168.1.21:50052
datas pool discover                # what will be used: linked devices + the ones you named
datas run <model-id> --pool        # llama-server … --rpc 192.168.1.20:50052,192.168.1.21:50052
```

**Datas cannot know how much memory a hand-listed worker offers**, so it does not add it to
the recommendation: `datas recommend --pool` counts linked devices only. With hand-listed
workers you pick the AI (`datas catalog list`) and llama.cpp spreads it over the devices;
if it does not fit, the engine says so when it starts.

Without `--host`, the worker listens on `127.0.0.1` only: that is for reaching it through a
tunnel of your own (SSH, WireGuard). `datas pool nodes --set ""` clears the list.

## How it works

- Each worker runs `ggml-rpc-server -H <host> -p 50052 -t <threads> -c`, offering the
  memory left after its own headroom.
- The head node passes `--rpc host:port,…` to `llama-server`. llama.cpp then
  distributes weights and KV cache across local and remote devices in proportion to
  each device's memory; each host may run a different backend (CUDA on one, Metal on
  another, CPU on a third).
- The recommender's pool budget (`pool_budget()`) is `Σ (ram_budget + vram_budget)` over
  the nodes whose memory is known — linked devices; placement `pool`, speed class from
  active bytes (`ok` ≤ 5 GiB, `slow` ≤ 12 GiB, else `crawl`).

## What to expect

- **Memory adds up. Speed does not.** Every generated token crosses the network at each
  device boundary. On Wi-Fi expect a few tokens/s for dense 30B-class models; wired
  gigabit is much better; 2.5/10 GbE approaches single-machine speeds.
- **MoE models shine** (Qwen3.6 35B-A3B, gpt-oss 120B, Gemma 4 26B-A4B, Nemotron
  Lightning): few active parameters per token means little traffic per token.
- **Phones are poor workers** (Wi-Fi latency, aggressive background killing, thermal
  throttling). They make fine *clients* of a pool though: point the phone's Datas at the
  head node as a remote provider (`http://<head>:8421/v1`).
- **Same build everywhere.** The RPC protocol version is tied to the llama.cpp build.
  Datas pins a tag (`datas runtime info`) and `datas pool discover` shows each worker's.
  Fix with `datas runtime pin <tag>` + `datas install` on the odd node.

## Security

The RPC protocol has **no authentication or encryption**. A worker will serve memory and
compute to anyone who can reach its port. Use it only on a network you fully trust or
through your own tunnel (WireGuard, Tailscale, SSH); Datas prints this warning when a worker
starts on the network. Linked devices ([DEVICES.md](DEVICES.md)) do not have this problem:
there the worker listens on `127.0.0.1` and is reached only through the encrypted link.

## Alternative: exo

[exo](https://github.com/exo-explore/exo) (Apache-2.0) automatically discovers devices
and shards a model across them with an OpenAI-compatible API, and is particularly strong
on clusters of Apple Silicon Macs. It uses MLX-format models (GGUF needs conversion) and
does not run on Windows. Datas chose llama.cpp RPC as the default because it keeps one
model format and runs everywhere; an exo backend for all-Mac pools is on the roadmap.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Worker not counted | it is not in `datas pool nodes`; or it was started without `--host` and listens on `127.0.0.1` only; or a firewall blocks port 50052 |
| `llama-server` fails with RPC protocol error | tag mismatch between nodes |
| Very slow | dense model over Wi-Fi; try an MoE model or wire the nodes |
| Worker exits on load | its headroom too small for its share; raise headroom on the worker |
