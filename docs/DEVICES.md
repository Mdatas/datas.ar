# Linking your own devices

Datas can connect the computers **you** own so that they:

- **share chats** — the same list of chats on each of them (Remember mode only);
- **use each other's AI** — a small laptop or a phone chats with the AI running on the
  desktop. Only the words travel, so it is as quick as the desktop itself;
- **share out a long document** — each linked computer with an AI writes some of the parts.

Adding up the memory of several devices to run one bigger AI was **removed in 0.9**. Every
word needed many trips over the network, so it was much slower than a smaller AI on one
device, and it promised more than it gave.

Only devices you pair yourself can connect. There is no Datas account and no Datas server.

Strangers' devices are **not** supported: whoever computes part of an answer sees what you
asked, and no technology available on ordinary computers and phones prevents that today.

## Pairing, step by step

1. Open **Devices** on both computers and switch on *Let my other devices connect to this one*.
2. On computer A press **Show a code**. It shows a 12-symbol code (for example
   `YW6V-YLGD-UG69`) and its address (for example `192.168.1.20:8424`).
3. On computer B type that address and that code, and press **Link**.

The code works once, for ten minutes, and is cancelled after five wrong attempts. Devices on
the same network also appear under *Seen on this network*, so the address can be filled in
with one click.

From the command line: `datas-cli link status | code | pair <address> <code> | unlink <id> | sync`.

## Phones and tablets

The Datas app for Android has a card called **My computers** (see [MOBILE.md](MOBILE.md)).
There is no iPhone app.

1. On the computer: *Devices → Show a code*.
2. On the phone: *My computers → Link a computer*. Computers on the same Wi-Fi are listed;
   tap yours (or type the address the computer shows) and type the code.
3. Tap **Open** next to the computer. The phone now shows that computer's Datas — its chats,
   its AIs, helpers, documents, Learn — and the answers are written by the computer's AI.

So a phone with little memory uses the big AI at home. The phone app also still runs a small
AI of its own, without any connection.

**What a linked phone may do** is decided at the computer, per phone, with one switch on the
Devices screen: *May open Datas on this computer*. With it on, the phone can use Datas there
as if you sat in front of it — with these exceptions, which are refused because a phone can
be lost or borrowed:

- the computer's microphone, camera, screen and other hardware;
- opening files, folders or programs on the computer;
- linking or unlinking devices, adding connections (MCP), erasing everything Datas remembers,
  installing an update;
- letting the agent run commands.

**If a phone is lost:** press *Unlink* next to it on the computer's Devices screen. From that
moment the phone is refused.

Limits today: the phone has to reach the computer — the same Wi-Fi, or a private network
between your devices (WireGuard, Tailscale); files saved from an answer stay on the computer;
talking to the AI by voice is not available from the phone yet; chats made with the phone's
own small AI are not shared with the computer. Neither app has been tried on a physical phone
by the project yet (see [MOBILE.md](MOBILE.md)).

## Opening the Datas of another computer

For a computer without a screen — a Raspberry Pi in a corner, a home server, a NAS — or just
to look after the computer in the other room: one linked computer can show the Datas of
another, in a window of its own.

1. **At the computer to be opened**, allow it: *Devices →* the other computer *→ May open
   Datas on this computer*. Without a screen: `datas-cli link window "Laptop" on`.
   It is off until you switch it on, for each computer separately.
2. **At the computer in front of you**: *Devices →* that computer *→ Open its Datas*
   (or `datas-cli link open "Pi"`).

The window says at the bottom whose Datas it is and where the chats are kept. You can chat
with its AIs, get or change its AI, use helpers and documents, read its results. It travels
through the same encrypted link as everything else, and the opened computer treats it
**exactly like a phone**: no microphone, camera, screen or other hardware of that computer,
no opening its files or programs, no linking or unlinking, no commands for the agent. Those
stay things you do at that computer itself (for one without a screen: with `datas-cli`
there).

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

### Phones: a secret instead of a certificate

A phone app does not make a certificate. When linking, it invents a long random secret
(256 bits) and uses the one-time code to prove that the secret is its own, while the computer
proves it knows the code too — the same exchange as between computers, with the fingerprint
of the phone's secret in the place of a certificate. Afterwards the phone:

- connects with TLS 1.3 and accepts **only** the exact certificate the computer had when they
  were linked (so another device at that address is refused);
- shows its secret inside that encrypted connection.

The computer stores only a fingerprint (SHA-256) of the secret, so its list of linked devices
does not contain anything that could be used to pretend to be the phone. The phone keeps the
secret in the app's private storage.

### What travels on the link

| Purpose | What is sent |
|---|---|
| Presence | Name, system, Datas version, engine version, name of the AI running (if any). Asked every 20 seconds. |
| Chat sync | The chats themselves. Newest change wins; a deleted chat is deleted everywhere (a small "deleted" marker travels so it does not come back). Never in Forget mode. |
| Using another device's AI | Your messages and the answers, as `/v1` requests. The other device processes them with its local AI and keeps nothing unless that chat is also synced. The same goes for the parts of a long document shared out between devices. |
| Opening another computer's Datas | Everything that window shows and sends, as ordinary requests to that computer's Datas, inside the encrypted link. |

## Limits, stated plainly

- **Phones are a window, not a full member yet.** A linked phone shows and uses a computer's
  Datas; it does not share the chats of its own small AI. Android 10 or newer.
- **One answer cannot be split and written in parallel — a long document can.** *Tools →
  Long documents → Share the work with my linked devices* gives each part to whichever
  device is free: this one and every linked computer that has an AI of its own ready. It
  finishes sooner; the parts are written by different AIs, so the style can vary from part
  to part; a device that drops out gives its part back and the rest carry on. The parts are
  cut for the smallest working memory among them. Other kinds of work (several chats or
  agent tasks at once across devices) are not shared out yet.
- **Same network works directly. Different places need a reachable address.** There is no
  relay server by design, because a relay would be a third party. Use a private network
  between your devices (WireGuard or Tailscale, for example) or open port 8424 on the router
  of the device that shows the code. The link stays encrypted end to end either way.
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
- Messages: a 4-byte length followed by JSON; after a `v1` or `window` request the same
  connection carries raw bytes.
- Operations: `pair`, `info`, `sync`, `v1` (OpenAI-compatible request to the local AI), and
  `window` (the
  connection is joined to the local service on `127.0.0.1`) — for phones, and for a computer
  that was allowed to (`"window": true` on that peer in `peers.json`).
- A phone pairs with `{"op":"pair","app":true,"id":<SHA-256 of its secret>,…}` and later
  sends `"auth": <secret>` in its first message instead of presenting a certificate; it may
  only ask for `info` and `window`. The service learns which of its connections come from a
  phone (`core.remote_clients`) and applies `remote_refusal()` in `datas/server/app.py`.
- The phone's side: [`android/…/ar/datas/link/LinkClient.java`](../android/app/src/main/java/ar/datas/link/LinkClient.java)
  (plain Java, standard library only) and the same in Python, [`tests/phone.py`](../tests/phone.py).
  `tests/test_phone_link.py` compiles the Java and runs it against a real Datas.
- A computer showing another's Datas: `LinkManager.open_window()` makes a door on
  `127.0.0.1` whose connections are each joined to a `window` request on the link
  (`tests/test_link.py` runs it between two real Datas).
- Sharing a long document out: `datas/tools.py` (`helpers`, `_share_out`) sends each part as
  a `v1` request to whichever device is free.
- With a real AI on both sides: the weekly and per-release run (`scripts/e2e_real.py --link`)
  starts a second Datas, links the two with a code, answers on one with the AI of the other,
  shares a long document out between both AIs and opens one's window from the other — on
  Windows, macOS, Linux and ARM Linux. One exception: the shared document is not run on the
  Mac test machine, where two engines would share one *virtual* graphics chip and drop to
  about two words a second; real Macs have one engine each.
- Rediscovery after an address change: mDNS service `_datas-link._tcp` carrying the device id.
- Files in `<data folder>/link/`: `device.key` (private, mode 600), `device.crt`,
  `peers.json` (name, address and certificate of each paired computer; name and secret
  fingerprint of each paired phone).
