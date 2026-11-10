# Linking your own devices

Datas can connect the computers **you** own so that they:

- **share chats** — the same list of chats on each of them (Remember mode only);
- **lend each other memory** — a bigger AI fits when two or three devices add up their memory;
- **use each other's AI** — a small laptop can chat with the AI running on the desktop;
- **carry on alone** — if a device drops out mid-chat, the one you are using continues with
  the best AI that fits on it.

Only devices you pair yourself can connect. There is no Datas account and no Datas server.

Strangers' devices are a different matter and are **not** supported: see [P2P.md](P2P.md) for
why that cannot be made private today.

## Pairing, step by step

1. Open **Devices** on both computers and switch on *Let my other devices connect to this one*.
2. On computer A press **Show a code**. It shows a 12-symbol code (for example
   `YW6V-YLGD-UG69`) and its address (for example `192.168.1.20:8424`).
3. On computer B type that address and that code, and press **Link**.

The code works once, for ten minutes, and is cancelled after five wrong attempts. Devices on
the same network also appear under *Seen on this network*, so the address can be filled in
with one click.

From the command line: `datas-cli link status | code | pair <address> <code> | unlink <id> | sync`.

## How it is protected

Words used below: **TLS** (Transport Layer Security) is the web standard that encrypts
connections — the "https" of banking sites. A **certificate** is a device's public identity
card; the matching **private key** never leaves the device.

| Step | What happens |
|---|---|
| Identity | Each device creates its own key (elliptic curve P-256) and a self-signed certificate the first time linking is switched on. The device's identity is the SHA-256 fingerprint of that certificate. |
| Pairing | The code never travels. Each side proves it knows the code with an HMAC-SHA256 over **both** certificates' fingerprints plus fresh random numbers, keyed by the code stretched with PBKDF2 (300,000 rounds). A device in the middle that does not know the code cannot pass, and cannot swap in its own certificate, because the fingerprints are part of what is proven. |
| After pairing | Each device stores the other's certificate; the code is thrown away. |
| Every connection | TLS 1.3 with a certificate on **both** sides ("mutual TLS"). Each side accepts only the exact certificate it stored at pairing ("pinning"). No certificate authority is involved. |
| Strangers | A device that was never paired is refused during the TLS handshake, before it can ask for anything. |

What an outsider sees — your Wi-Fi router, your internet provider, someone on the same
network: that two of your devices exchange encrypted data, how much, and when. Not the
content.

### What travels on the link

| Purpose | What is sent |
|---|---|
| Presence | Name, system, Datas version, engine version, memory on offer, name of the AI running (if any). Asked every 20 seconds (8 while memory is being shared). |
| Chat sync | The chats themselves. Newest change wins; a deleted chat is deleted everywhere (a small "deleted" marker travels so it does not come back). Never in Forget mode. |
| Shared memory | llama.cpp's own protocol between the device that runs the AI and the ones lending memory, inside the encrypted tunnel. The helper program on the lending device listens on `127.0.0.1` only — it is reachable through the tunnel and nowhere else. |
| Using another device's AI | Your messages and the answers, as `/v1` requests. The other device processes them with its local AI and keeps nothing unless that chat is also synced. |

## Limits, stated plainly

- **Computers only, for now.** The Android app cannot link yet.
- **Bigger, not faster.** Shared memory lets a larger AI fit. Every word still passes
  through all the devices, so the speed is set by the slowest one and by the network. A cable
  or good Wi-Fi matters.
- **One answer cannot be split and written in parallel.** Running many independent tasks at
  once across devices ("farm mode") is on the roadmap, not in this version.
- **Same network works directly. Different places need a reachable address.** There is no
  relay server by design, because a relay would be a third party. Use a private network
  between your devices (WireGuard or Tailscale, for example) or open port 8424 on the router
  of the device that shows the code. The link stays encrypted end to end either way.
- **Same engine on both.** Sharing memory needs the same llama.cpp version on every device;
  Devices says so when they differ, and Settings → Updates brings them in line.
- **A device that is running its own AI lends no memory** while it does.
- **Chat sync is "newest change wins".** If you edit the same chat on two devices while they
  are disconnected, the later edit replaces the earlier one.
- **Trust is all-or-nothing between paired devices.** A paired device can read synced chats
  and use the AI. Pair only devices you control, and unlink a device you sell or lose
  (*Devices → Unlink* on any of the others).

## What it does not protect against

- Someone who already controls one of your paired devices (malware, a stolen unlocked laptop).
- Someone who reads the code off your screen **and** reaches your device on the network
  during the ten minutes it is valid.
- Traffic analysis: an observer can tell that your devices talk and how much.

## For developers

Code: [`datas/link/__init__.py`](../datas/link/__init__.py). Tests: `tests/test_link.py`.

- Listener: TCP port 8424 (`cfg.link_port`), TLS 1.3 only, started when linking is on.
- Messages: a 4-byte length followed by JSON; after an `rpc` or `v1` request the same
  connection carries raw bytes.
- Operations: `pair`, `info`, `sync`, `rpc` (tunnel to the local `ggml-rpc-server` on
  `127.0.0.1`), `v1` (OpenAI-compatible request to the local AI).
- Rediscovery after an address change: mDNS service `_datas-link._tcp` carrying the device id.
- Files in `<data folder>/link/`: `device.key` (private, mode 600), `device.crt`,
  `peers.json` (name, address and certificate of each paired device).
- The older, manual way of pooling memory without pairing is described in
  [POOLING.md](POOLING.md); it is unencrypted and meant only for a network you fully control.
