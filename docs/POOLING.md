# Pooling devices

Run one model across several machines so their memory adds up. Built on llama.cpp's RPC
backend; Datas adds discovery, budgeting and the same one-click flow.

## Quick start

```bash
# every extra device (laptop, old PC, Mac mini …)
pipx install datas-ar
datas pool worker            # starts ggml-rpc-server on :50052 and advertises itself

# the device you chat from
datas recommend --pool       # budget = this device + every worker found on the LAN
datas run --pool             # llama-server … --rpc 192.168.1.20:50052,192.168.1.21:50052
```

Or in the UI: *Pool → Scan LAN*, then set *Pool: This device + LAN workers* and the
recommendation recomputes with the pooled budget.

Workers not on the same broadcast domain can be listed by hand:
`datas pool nodes --set 10.0.0.5:50052,10.0.0.6:50052` (merged with mDNS results).

## How it works

- Each worker runs `ggml-rpc-server -H 0.0.0.0 -p 50052 -t <threads> -c` and publishes a
  `_datas-rpc._tcp.local.` mDNS record with: llama.cpp tag, backend, RAM/VRAM it offers
  (its own headroom already subtracted), Datas version.
- The head node passes `--rpc host:port,…` to `llama-server`. llama.cpp then
  distributes weights and KV cache across local and remote devices in proportion to
  each device's memory; each host may run a different backend (CUDA on one, Metal on
  another, CPU on a third).
- The recommender's pool budget is `Σ (ram_budget + vram_budget)` over nodes
  (`pool_budget()`), placement `pool`, speed class from active bytes (`ok` ≤ 5 GiB,
  `slow` ≤ 12 GiB, else `crawl`).

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
  Datas pins a tag (`datas runtime info`) and the UI marks workers whose tag differs in
  red. Fix with `datas runtime pin <tag>` + `datas install` on the odd node.

## Security

The RPC protocol has **no authentication or encryption**. A worker will serve memory and
compute to anyone who can reach its port. Use pools only on a LAN you trust or over a
VPN (Tailscale, WireGuard). Datas prints this warning when a worker starts.

## Alternative: exo

[exo](https://github.com/exo-explore/exo) (Apache-2.0) automatically discovers devices
and shards a model across them with an OpenAI-compatible API, and is particularly strong
on clusters of Apple Silicon Macs. It uses MLX-format models (GGUF needs conversion) and
does not run on Windows. Datas chose llama.cpp RPC as the default because it keeps one
model format and runs everywhere; an exo backend for all-Mac pools is on the roadmap.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Worker not discovered | mDNS blocked (guest Wi-Fi, firewall); use `datas pool nodes --set` |
| `llama-server` fails with RPC protocol error | tag mismatch between nodes |
| Very slow | dense model over Wi-Fi; try an MoE model or wire the nodes |
| Worker exits on load | its headroom too small for its share; raise headroom on the worker |
