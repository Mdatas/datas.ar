# Datas.ar

**Your own AI, on your own computer. One install, one icon, a few clicks.**

Datas puts an AI (Artificial Intelligence) assistant — the kind you know from ChatGPT — on
your own computer. It runs there, offline, for free. Nothing you type leaves your device
unless *you* switch the internet on for a chat or choose a paid online service.

It is made for people who have never heard the words "model", "GPU" or "quantization".
Datas looks at your device, picks the best open AI it can carry **without slowing everything
else down**, downloads it and opens a chat. It stays neutral: it tells you plainly what your
device can and cannot do, and the choices are yours.

## Start in three steps

1. **Install and open Datas.** It asks one thing: *Remember* (chats and notes stay on this
   device) or *Forget* (nothing is written down).
2. **Add an AI.** Datas reads your working memory (RAM), graphics card (GPU) and disk, asks
   what you want to do besides chatting and writing — look at pictures, write code, do tasks
   with files and the web, talk and listen, make pictures and video — and how much of the
   device the AI may use. It shows one recommendation in plain words: why this one, what it
   cannot do, who made it, how big the download is. Every other AI that fits is listed too.
3. **Chat.** A small AI (about 0.4 GB) starts first, so you can talk while the chosen one
   downloads. Even before that, the built-in guide answers questions about your device.

## What is in the window

| Screen | What it is for |
|---|---|
| **Chats** (left side) | Every chat, with search. Start a new chat with any AI you have; each chat remembers which AI it used. |
| **My AIs** | The AIs on this device, each with a plain summary (good for, keep in mind, memory and disk used), lighter and stronger versions, a desktop shortcut, and *Use a model file I already have*. |
| **Add an AI** | The recommendation, plus *What this device can do*: a plain yes / slow / no for each kind of task. Nothing is hidden or greyed out. |
| **Create** | Pictures and short videos made on this device. |
| **Tools** | Recording → text with subtitles, text → audio, summarise or translate long documents; the agent; cameras, printers and other hardware; the open programs found on this computer; connections; bigger creative tools. |
| **Devices** | Link your own computers with a one-time code. |
| **Learn** | AI from zero to expert, in English and Spanish. |
| **Settings** | Privacy, language and look (day or night), the AI, voice, paid online services, updates. |
| **About Datas** | Version, everything Datas is built on, technical logs. |

### In a chat

- **Helpers.** 43 ready ones — the same AI prepared for one kind of job (write a letter,
  explain a contract, plan a week, review code…) — and you can make your own.
- **Documents.** Attach PDF, Word, Excel, PowerPoint, web pages or text and ask about them;
  pictures too when the AI can see. → [docs/EVERYDAY.md](docs/EVERYDAY.md)
- **A photo or your screen.** The camera button adds a photo from the camera or a picture of
  what is on your screen, for an AI that understands pictures.
- **Save an answer** as Word, Excel, PowerPoint, PDF, web page, Markdown or plain text — or
  print it on paper.
- **Internet, per chat.** Off until you switch it on; the AI shows which pages it used.
- **Voice.** Talk to it and have answers read aloud, all on this device.
- **Paid AIs, optionally.** Paste an API key (Application Programming Interface key: a
  password-like code from OpenAI, Google, Anthropic, Groq…) and use the same chat with their
  AI. The key stays on your computer; that company then sees what you send it.

### Your devices, together

Link the computers you own with a one-time code. They can then keep the same chats, lend
each other memory so a bigger AI fits, and use each other's AI; if one drops out, the one
you are on carries on alone. An Android phone links the same way and shows the computer's
Datas, so a small phone uses the big AI at home. The link is encrypted with the web's standard (TLS 1.3) and
only devices you paired can connect — no account, no server in the middle. Strangers'
devices are not supported, because that cannot be made private today.
→ [docs/DEVICES.md](docs/DEVICES.md) · [docs/P2P.md](docs/P2P.md)

### Learn

14 short lessons written for Datas, a 42-word glossary and 55 hand-checked courses, videos,
books, reports and official texts, arranged in 18 paths: what AI is, using it well, how it
works, building with it, its history, who is who, the public debates and the rules, and how
to bring it into a business, a school, a social project or a government office.
→ [docs/LEARN.md](docs/LEARN.md)

### The agent and your other programs

The agent works step by step in its own folder and in the folders you tick: read, write,
sort and convert files, look things up, and — only if you allow it — run commands. It asks
before anything risky and "delete" is a move to a trash folder. It can use the open programs
already on your computer (LibreOffice, FFmpeg, Inkscape, Blender, ArtCraft…) and any program
that speaks the Model Context Protocol (MCP), an open standard for giving tools to an AI.
→ [docs/AGENTS.md](docs/AGENTS.md) · [docs/PROGRAMS.md](docs/PROGRAMS.md)

### Cameras, printers and the things around you

When you ask, Datas can take a photo, look at your screen, print, talk to a board on a USB
cable (Arduino, ESP32, a 3D printer), read sensors and switch things through your own
smart-home hub (MQTT, Home Assistant), read and write industrial devices (Modbus), and list
what is on your network (printers, NAS, Raspberry Pi). For the agent it is one switch, off
until you turn it on; anything that looks at you or acts on the world asks first. The mouse
and keyboard are a second, experimental switch. None of it can be reached from a linked
phone. → [docs/HARDWARE.md](docs/HARDWARE.md)

### Updates you can undo

Nothing updates by itself. *Settings → Updates* checks for you; the app, the AI engine, the
picture engine and the list of AIs each update separately and each can go back to the version
before. Your AIs, chats and settings are kept. → [docs/UPDATES.md](docs/UPDATES.md)

## Install

| System | How |
|---|---|
| **Windows 10/11** | `Datas-Setup-<version>.exe` from the [Releases](https://github.com/Mdatas/datas.ar/releases) page — one file. Double-click it: a window with **Install · Repair · Uninstall · Exit**. Install replaces any earlier copy with a clean one and keeps your AIs, chats and notes; Uninstall asks whether to keep or delete them. No administrator password. |
| **Linux** | Debian/Ubuntu/Mint family: `datas_<version>_amd64.deb` (double-click). Arch/Manjaro/CachyOS family: `datas-bin-<version>-1-x86_64.pkg.tar.zst` (`sudo pacman -U …`). Others: `datas-<version>-linux-x64.tar.gz` + `./install.sh`. Details in [`installer/linux/README.md`](installer/linux/README.md). |
| **macOS 12+** | `Datas-<version>.dmg` — drag Datas to Applications; the first time **right-click → Open**. Apple Silicon runs the AI on the graphics chip. Details in [`installer/macos/README.md`](installer/macos/README.md). |
| **Android** | `Datas-release.apk` from the Releases page (Android 8+, arm64). It runs a small AI on the phone and, under *My computers*, links to your computers and uses their Datas (Android 10+). → [`android/`](android/README.md) |
| **Anything with Python 3.10+** | `pip install datas-ar && datas` |

Needs a 64-bit computer (or an arm64 phone). No account. The first start downloads the AI
engine (llama.cpp, 30–200 MB depending on your graphics card); each AI is a one-time download
of 0.4–20 GB depending on what fits.

Until a release is published, the installers are produced by the project's GitHub Actions
(*windows-installer*, *desktop-installers*) on every change.

## What is not there yet

- **The installers carry no paid certificate.** Windows and macOS show a warning on first
  start. Every release file does have a checksum and a signed record of where it was built;
  what the paid certificates need is in [docs/SIGNING.md](docs/SIGNING.md).
- **Phones**: Android links to your computers but has not been tried on a physical phone by
  the project yet; the iPhone app is being written and needs an Apple Developer account to
  reach a phone.
- **Linked devices make a bigger AI fit, not a faster one.** Splitting many tasks across
  devices is planned.
- **Hardware has been tested against stand-ins, not the real things**: the test machines
  have no camera, printer, Arduino, Home Assistant or PLC. See what was and was not tested in
  [docs/HARDWARE.md](docs/HARDWARE.md#how-it-was-tested-and-what-was-not).
- **Some texts are English only**: the limits and comparisons written for each AI, and many
  technical messages. The window itself is fully in English and Spanish, and so are the
  hardware messages and the refusals.

More in [docs/ROADMAP.md](docs/ROADMAP.md).

## For developers

Datas is deliberately a thin layer: the engine is [llama.cpp](https://github.com/ggml-org/llama.cpp),
the AIs are the open-weight community's, and the choice of AI is plain arithmetic you can
read in [`datas/recommend/engine.py`](datas/recommend/engine.py) — no AI picks the AI.

| | |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | layers, data flow, code map |
| [UI.md](docs/UI.md) | the window: files, design rules, how to add a screen or a text |
| [RECOMMENDER.md](docs/RECOMMENDER.md) · [HARDWARE_DETECTION.md](docs/HARDWARE_DETECTION.md) | the memory arithmetic; what is read from the device, per system |
| [CATALOG.md](docs/CATALOG.md) | the 27 verified AIs, the format, how to add one |
| [RUNTIME.md](docs/RUNTIME.md) · [UPDATES.md](docs/UPDATES.md) | llama.cpp builds, pinning, updates and going back |
| [PRIVACY.md](docs/PRIVACY.md) · [SECURITY.md](docs/SECURITY.md) · [SIGNING.md](docs/SIGNING.md) | what is stored where; how the app is protected and what it does not protect against; what is signed |
| [DEVICES.md](docs/DEVICES.md) · [POOLING.md](docs/POOLING.md) · [P2P.md](docs/P2P.md) | linked devices; the older manual pooling; why strangers' devices are ruled out |
| [EVERYDAY.md](docs/EVERYDAY.md) · [LEARN.md](docs/LEARN.md) | helpers, documents, saving answers; the Learn screen and how its links are checked |
| [AGENTS.md](docs/AGENTS.md) · [PROGRAMS.md](docs/PROGRAMS.md) · [APPS.md](docs/APPS.md) | the agent and its permissions; programs, connections (MCP), ArtCraft; bigger creative tools |
| [HARDWARE.md](docs/HARDWARE.md) | cameras, the screen, printers, boards, smart home, industrial devices, mouse and keyboard |
| [VIDEO.md](docs/VIDEO.md) · [PROVIDERS.md](docs/PROVIDERS.md) · [MOBILE.md](docs/MOBILE.md) | pictures and video; paid services and the `/v1` address; phones |
| [API.md](docs/API.md) | the local HTTP interface |
| [ROADMAP.md](docs/ROADMAP.md) · [CREDITS.md](docs/CREDITS.md) · [CONTRIBUTING.md](CONTRIBUTING.md) | what is next; who Datas is built on; how to help |

```bash
git clone https://github.com/Mdatas/datas.ar && cd datas.ar
pip install -e ".[dev]" && pytest   # about 170 tests, about a minute; one runs a real llama-server on a tiny model
datas selftest                      # checks this copy: window files, lessons, documents, device link, local service, hardware parts
datas open --selfcheck out.json     # opens the real window, checks every screen shows, writes a report
datas-cli --help                    # scan | recommend | run | chat | agent | link | things | provider | runtime | catalog | doctor …
```

A command line, a local interface (`http://127.0.0.1:8420/api/…`) and an OpenAI-compatible
address (`http://127.0.0.1:8420/v1`) are there for people who want them; the window never
shows them.

## License

GPL-3.0-or-later. The AIs keep their own licences, shown on every card; everything Datas is
built on is listed in *About Datas* and in [docs/CREDITS.md](docs/CREDITS.md).
