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

The Datas app for Android has a card called **My computers** (see *Phones* on this page).
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
by the project yet (see *Phones* on this page).

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

## Phones and tablets

### Android — the app (`android/`)

Two things in one app:

- **My computers** — link the phone to a computer of yours that has Datas (one-time code,
  encrypted, no account) and use that computer's Datas from the phone: its AIs, chats,
  helpers, documents and Learn. Described above, under *Phones and tablets*.
  Needs Android 10 or newer.
- **On this phone** — scan the phone → recommend a small AI → download → chat, with nothing
  leaving the phone. Same catalog file as the desktop, a port of the recommender, Android's
  DownloadManager for the files, and the official llama.cpp Android build inside the APK
  (about 27 MB). The chat here is still llama.cpp's own page, not the Datas window.

Get it: the `android-apk` workflow builds the APK on every change and attaches it to each
release — see [android/README.md](../android/README.md).

Status, honestly: the link code is tested on every change against a real Datas (the tests
compile it and pair, open the window, get refused where a phone should be). The app is
compiled by the build. **It has not been tried on a physical phone by the project yet** —
tell us what happens on yours.

### Android — alternative path via Termux

[Termux](https://termux.dev) (F-Droid or GitHub release, not the Play Store build) gives
Android a real shell with Python. The llama.cpp project publishes `android-arm64` builds
on every release, and Datas selects them automatically (`os=android`).

```bash
pkg update && pkg install python python-pip
pip install datas-ar
datas serve --no-browser          # then open http://127.0.0.1:8420 in Chrome
## or
datas run && datas chat
```

What Datas does differently on a phone:

- **Headroom defaults to 40 %** — Android kills memory-hungry apps without warning.
- **Context defaults are honoured but 4k is wiser** on 8 GB devices; pick it in the UI.
- Picks: 8 GB → Phi-4 mini Q6 / Qwen3 4B Q4; 12 GB → Gemma 4 E4B Q4; 16 GB → Qwen3 8B Q4.
- Backend: the `android-arm64-snapdragon` build is chosen on Qualcomm SoCs (Adreno/Hexagon
  acceleration), the generic `android-arm64` otherwise. GPU memory is unified: RAM is
  the budget.
- Battery: Datas records `on_battery`; generation is CPU-heavy, so expect heat. Keep the
  phone plugged for long sessions.

Known rough edges: Termux's `wake-lock` is needed to keep the server alive in the
background (`termux-wake-lock`); some vendors' background limits still kill it after a
while. Mark this experimental.

#### Native app notes

The native app in `android/` is the thin-shell design: a Kotlin port of the recommender
(no Python on the phone), a foreground service owning the `llama-server` process, and
the engine's web UI in a WebView. Open-source references for the next steps (file
picker, vision, Play Store packaging): PocketPal AI (MIT) and Google AI Edge Gallery
(Apache-2.0).

### iPhone and iPad

Not available: Apple only allows apps signed with a paid Apple developer account, and the project has none. The iPhone app (it linked to your computers and used their Datas) was removed in 0.9; its code is in the project history (version 0.8.1) and comes back with an account.

An AI on the iPhone itself would be built on the `llama-<tag>-xcframework.zip` that llama.cpp
ships with every release; iOS cannot run a downloaded engine program the way Android does.
Not started.

## Small computers without a screen: Raspberry Pi, home servers, NAS

Datas can run on a small computer that sits in a corner with no screen, keyboard or mouse,
and be used from your phone or from your other computers. That computer then holds the AI,
the chats and the scheduled tasks, and is on all day.

Words used here: **ARM** is the kind of processor in phones, in the Raspberry Pi and in many
small servers ("arm64" or "aarch64" when it is 64-bit). A **NAS** (network-attached storage)
is a box of disks that shares folders on your network. A **service** is a program that
starts with the computer and runs without a window.

### What to expect

Datas does not pretend. A small computer runs small AIs, slowly. Before anything else:

```
datas-cli scan         what this computer has (memory, processor, graphics)
datas-cli recommend    which AIs fit, and which is the best one for it
```

The same plain verdicts as in the window: runs well, runs slowly, does not fit. A second,
stronger computer of yours can lend its AI through the link (see below) — then the small one
is the door and the big one does the thinking.

### Install

| Computer | File |
|---|---|
| Raspberry Pi 4 or 5 with a 64-bit system (Raspberry Pi OS "Bookworm" or newer), other 64-bit ARM boards and servers with Debian 12 / Ubuntu 22.04 or newer | `datas_<version>_arm64.deb` — `sudo apt install ./datas_<version>_arm64.deb` |
| The same, without administrator rights, or another Linux for 64-bit ARM | `datas-<version>-linux-arm64.tar.gz` — unpack, `./install.sh` |
| A small PC (Intel/AMD) used as a server | the normal `datas_<version>_amd64.deb` |

The ARM package has no window of its own inside (that keeps it small and lets it run on
systems without a desktop). On a Raspberry Pi *with* a desktop, the **Datas.ar** entry of the
menu opens Datas in the web browser of the Pi.

A 32-bit system (the old default of Raspberry Pi OS) is not supported.

### Five commands

```
datas-cli service install     Datas starts now and every time the computer starts
datas-cli run                 downloads the best AI for this computer and starts it
datas-cli link code           shows an address and a one-time code
```

Then, on your phone: *Datas app → My computers → Link a computer*, type the address and the
code, and **Open**. You are now using the Datas of the small computer: its chats, its AI,
Add an AI, helpers, documents, Learn.

Or on another computer of yours with Datas: *Devices → I have a code*. After that the chat's
AI menu offers the AI of the small computer, and the two keep the same chats (see the start
of this page).

To look after the small computer from that other computer — get it another AI, read what its
scheduled tasks wrote — let it open the small one's Datas. On the small computer, once:

```
datas-cli link window "Laptop" on     "Laptop" is the name of the other computer
```

Then on the laptop: *Devices → the small computer → Open its Datas*. It opens in a window of
its own and says at the bottom whose Datas it is.

```
datas-cli service status      is it installed, running, started with the computer?
datas-cli service remove      stop starting it; AIs, chats and settings stay
```

`datas-cli run` notices that Datas is already running as a service and starts the AI there,
so there is never a second engine beside it.

#### On a Windows PC or a Mac

The same is in *Settings → Start Datas with the computer* (or `datas-cli service install`):
on **Windows** it is an entry in your own "Run" list (`HKEY_CURRENT_USER\…\Run`, where every
app that starts with Windows goes) that starts `Datas.exe serve --no-browser` with no window;
on **macOS** a LaunchAgent, `~/Library/LaunchAgents/ar.datas.service.plist`. Both start when
you log in, run as you, need no administrator, and are removed by switching it off (or
`datas-cli service remove`). Opening the Datas window then shows that same running Datas.

#### Starting before anyone logs in

A computer without a screen has nobody logging in. `service install` asks the system to start
your services at boot. If the system refuses that to a normal user, Datas says so and shows
the one command that needs the administrator:

```
sudo loginctl enable-linger <your user name>
```

#### What the service is

A *user* service of systemd (the part of Linux that starts programs): it runs as you, not as
the administrator. The file is `~/.config/systemd/user/datas.service` and contains one line
that matters: `ExecStart=… datas-cli serve --no-browser`. Nothing outside your own folders is
touched. After upgrading the package: `systemctl --user restart datas`.

### Who can reach it

- The service itself answers **only on the computer it runs on** (`127.0.0.1`). It is not
  open to your network.
- Your phone and your other computers reach it through the **link**: one port (8424),
  encrypted with TLS 1.3, only for the devices you paired with a one-time code.
  → this page, [SECURITY.md](SECURITY.md)
- A linked phone — or another computer showing this one's Datas — cannot use this computer's
  camera, printer or other hardware, cannot make the agent run commands, and cannot unlink
  or link devices. Those are done on the computer itself — here, from its command line.
- To use it from outside your home, put your devices on a private network of your own
  (WireGuard, Tailscale). Do not open the port to the internet.

`datas-cli serve --host 0.0.0.0` exists and puts the window on your network **without a
password and without encryption**; it is not needed for any of the above and is not
recommended.

### Hardware on a small computer

Everything in [HARDWARE.md](HARDWARE.md) works the same from the command line and for the
agent: USB cameras, printers the system knows, boards on USB/serial (Arduino, ESP32, Pico),
MQTT, Home Assistant, Modbus, the list of devices on the network.

```
datas-cli things list
datas-cli agent "read the temperature from the board on /dev/ttyACM0 and write it to today.txt" --devices
```

Not there yet, said plainly:

- the Raspberry Pi **camera module** on the ribbon cable (it is not a normal camera to the
  system; a USB camera is);
- the Pi's **GPIO pins** directly — connect a board by USB, or go through MQTT or Home
  Assistant;
- a ready-made app for **Synology, QNAP** or other NAS systems. Datas runs on a NAS where a
  Debian or Ubuntu system for 64-bit ARM or Intel/AMD can be installed (many allow a virtual
  machine or a container); the NAS's shared folders are used like any folder;
- a picture of the screen and the mouse and keyboard (there is no screen).

### How it was tested

Every change builds the ARM package on a 64-bit ARM machine with Ubuntu 22.04, runs the
app's self-test there, starts the service without a window, installs it as a systemd service,
asks it for a pairing code, removes it again, and installs the package on a clean Debian 12
(the system of Raspberry Pi OS "Bookworm"). The weekly test with a real AI also runs on ARM:
it downloads the engine and a small AI and checks a real answer.

**Not tested on the real thing**: a physical Raspberry Pi or NAS. The test machines are ARM
servers in a data centre, which have far more memory and no SD card.
