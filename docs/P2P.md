# Sharing compute with strangers (P2P) — an idea, not an option

**Decision (Nov 2026): Datas does not offer pooling with strangers' devices, because it
cannot be made private with today's technology. If it is not private, it is not an option.**
This page keeps the idea and the reasoning so it can be revisited when the facts change.

Short answer to "is it possible?": **yes, and done before — but not private**, and that is
the part that matters for Datas. Here is the honest picture.

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

## What Datas does instead

1. **Your own devices** (today): pooling on your home network — see POOLING.md.
2. **Devices you own elsewhere** (planned): the same pool over your own VPN (Tailscale /
   WireGuard). Still only machines that are yours.
3. **Public model-file sharing** (idea): a torrent/IPFS mirror of the catalog so downloads
   don't depend on one host. The files are public; no privacy issue.

## What Datas does not do

- **Strangers' compute without privacy** — technically possible (Petals), explicitly ruled
  out: the person running a layer could reconstruct what you asked.
- **Strangers' compute with privacy** — would require consumer devices with trusted
  execution hardware and remote attestation, or a practical homomorphic-encryption
  breakthrough. Neither exists in 2026. Revisit when one does.

## If you want to experiment now (your own devices only)

`docs/POOLING.md` + a Tailscale network between your own devices works today with no code
changes (`datas pool nodes --set <tailscale-ip>:50052`).
