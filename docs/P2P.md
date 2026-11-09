# Sharing compute with strangers (P2P) — is it possible?

Short answer: **possible, and done before — but not private**, and that is the part that
matters for Datas. Here is the honest picture.

## What exists

- **Petals** (BigScience, 2022–2024) ran BLOOM-176B and Llama-70B across volunteers' GPUs
  over the public internet: each node hosts a few transformer layers; your request hops
  node to node. It worked at a few tokens per second.
- **exo**, **llama.cpp RPC** (what Datas uses today): the same idea on a trusted LAN.
- BitTorrent-style **model distribution** (sharing the *files*) is trivially possible and
  private-enough — the files are public anyway.

## Why "encryption for privacy" doesn't solve it

Transformer inference needs the *activations* (the numbers flowing between layers) in the
clear on whatever device computes the next layer. You can encrypt the wire (TLS) — Petals
did — but the node still sees the activations, and activations can be inverted to recover
input text with high fidelity. So a stranger's GPU learns what you asked. Options:

| Approach | Private? | Practical in 2026? |
|---|---|---|
| TLS on the wire | hides from eavesdroppers only | yes |
| Split the model so no node sees the input layer | leaks less, still inferable | yes, weak |
| Fully homomorphic encryption (FHE) | yes | no — 10⁴–10⁶× slower for LLM-size matmuls |
| Secure multi-party computation (MPC) | yes | no — minutes per token for 7B-class models |
| Trusted execution environments (TEE): Intel TDX / AMD SEV-SNP CPUs, NVIDIA H100/Blackwell confidential computing | yes, if you trust the hardware vendor | yes on data-center GPUs; **not on consumer GPUs or phones** |

So a stranger-P2P network that is *private* today means: TEE-capable hardware on the
provider side (which consumer devices don't have), plus attestation so you can verify the
node is really running the code it claims. That is a cloud-provider product, not a
"friends' laptops" product.

## What *is* reasonable for Datas

1. **Trusted circles** (v0.3): pools over a VPN mesh (Tailscale/WireGuard) with family and
   friends you'd lend a laptop to anyway. Same RPC, authenticated by the VPN, encrypted on
   the wire, and the trust model is explicit: *these people could, in principle, read what I
   ask*. The UI should say exactly that.
2. **Public model-file sharing**: a torrent/IPFS mirror of the catalog so downloads don't
   depend on one host. No privacy issue.
3. **Strangers' compute without privacy**: possible, as Petals showed, for *non-sensitive*
   prompts, labelled loudly as such. Worth it only if the quality jump is big (120B+
   models); the latency makes dense models painful and MoE models tolerable.
4. **Strangers' compute with privacy**: wait for consumer TEE GPUs or a practical FHE
   breakthrough. Not on the roadmap as a promise; tracked as research.

## If you want to experiment now

`docs/POOLING.md` + a Tailscale network between your devices gives you item 1 today with
no code changes (`datas pool nodes --set <tailscale-ip>:50052`).
