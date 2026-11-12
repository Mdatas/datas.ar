# Privacy: remember or forget

Datas has two modes. The user picks one on first start and can switch any time in
*Settings → Privacy*. The setting is `memory_mode` in `config.json`. `<home>` below is
Datas' data folder (*About Datas* shows where it is and opens it).

## Remember me (`memory_mode = remember`)

| What | Where | Who can read it |
|---|---|---|
| Conversations | `<home>/chats/<id>.json` | only this device (and the devices you linked, if you switched chat sync on); listed on the left of the window, with search |
| Notes about the user | `<home>/memory.md` — plain text, editable in Settings | given to the AI at the start of every chat so it "knows" the user |
| Documents always at hand | `<home>/context/` | the passages that match each question are given to the AI |
| Your own helpers | `<home>/assistants/` | only this device |
| What you marked as done in Learn | `<home>/learn.json` | only this device |
| Files you saved from answers | your Documents folder, in `Datas/` | ordinary files of yours |
| Technical logs | `<home>/logs/` (engine output and errors; never messages) | switchable off |

*Remember what matters from this chat* (the ⋯ menu of a chat) asks the running AI to list up
to 6 lasting facts the user *actually said* (`chats.LEARN_PROMPT`) and adds them to
`memory.md` with a date. Nothing is added by itself.
*Erase everything Datas remembers* (Settings) deletes chats, notes and the documents kept at
hand; installed AIs stay.

## Forget everything (`memory_mode = forget`)

- Nothing above is written. `save_chat`, `append_memory` are no-ops; the chat list says
  that chats are not kept, Learn does not record progress, and chat sync between devices is
  off.
- The engine starts with `--log-disable` and its output goes to the null device.
- The desktop window runs in private mode (no cookies/local storage persisted).
- Job logs exist only in memory for the current process.

What still exists in forget mode: the downloaded model files, the engine, `config.json`
(settings only), and the operating system's own traces (swap, etc.) which Datas cannot
control.

## Internet

Off by default. Each chat has its own switch; when on, the AI gets exactly two read-only
tools — `web_search` (DuckDuckGo results) and `fetch_url` — and the window shows every
lookup. The agent window has its own switch. Nothing is *sent* anywhere by these tools
beyond the search words or the address itself. Addresses inside your own network (router,
printer, other computers) are refused unless you allow them in Settings
(see [SECURITY.md](SECURITY.md)).

**Links you click** (in Learn, About, an AI's maker page) open in your usual browser, outside
Datas. From then on it is ordinary browsing: that website sees your visit as it would any
other. Datas adds nothing to the address and keeps no list of what you opened.

## Paid providers

An API key the user adds is stored in `config.json` on this device and sent only to the
base URL of that provider when the user chats through it. `GET /api/providers` never returns
keys. Using a paid provider means that company sees the conversation — the UI says so.

## Your linked devices

Devices you link yourself (*Devices*) talk over an encrypted connection (TLS 1.3, a pinned
certificate on both sides); there is no Datas account and no server in between. What travels:
presence (name, system, versions, memory on offer), the chats if you switched sync on, the
AI's internal numbers when memory is shared, and your messages when you use another device's
AI. Someone watching the network sees that your devices talk, how much and when — not what.
Details and limits: [DEVICES.md](DEVICES.md).

A linked **phone** shows this computer's Datas: what you type on the phone travels over the
same encrypted link and is handled, and kept, by the computer — nothing is stored on the
phone except the link itself (the computer's fingerprint and the phone's secret).

The older, hand-made way of pooling (`datas pool worker --host …`, [POOLING.md](POOLING.md))
is llama.cpp's own protocol with no password and no encryption: only for a network you fully
control.

## What Datas never does

No usage statistics, no analytics, no account, and nothing updates by itself. The outbound
connections are:

| To | When | What is sent |
|---|---|---|
| Hugging Face | you add an AI, voice or picture model | the request for that file (your internet address, like any download) |
| GitHub | the AI engine is downloaded; about twice a day while Datas runs, if *Keep Datas up to date by itself* is on (Settings → Updates); you press *Check for updates* or *Get ArtCraft*; FFmpeg is fetched because a camera or a recording needs it and the computer has none | the request for the file or for the public list of versions |
| A paid service | you added its key and chat through it | the conversation |
| The web | you switched internet on in a chat or for the agent | search words and page addresses |
| Your other devices | you linked them | see above |
| Your own hub and devices (MQTT broker, Home Assistant, Modbus devices) | you typed their address and the agent uses them | the message, request or value, to that address on your network |
| PyPI and the tool's own sources | you open a "bigger creative tool" | the download of that tool |

Nothing about you, your device or your use of Datas is sent to the project.

## Voice

Hearing and speaking happen on this computer: whisper.cpp turns your voice into text and Kokoro
turns answers into speech, both on the processor. What the microphone records is kept only in
memory while it is being understood and is dropped afterwards; the spoken answer is streamed to
the window and never written to disk. Nothing about voice changes between Remember and Forget
modes — there is nothing to store either way. The only downloads are the model files, from
Hugging Face (whisper) and GitHub (Kokoro), with exact sizes and checksums in `datas/catalog/media.json`.

## Camera, screen and other hardware

Datas does not watch or listen in the background. A photo is taken when you press the camera
button in a chat or when the agent asks and you allow it; the same for a picture of your
screen. → [HARDWARE.md](HARDWARE.md)

- A picture attached to a chat is part of that chat: it is kept with the chat in Remember
  mode (so you can read the chat again) and not kept in Forget mode. With an AI on this
  device it goes nowhere; with a paid online service it is sent to that company like the rest
  of the conversation.
- Pictures the agent takes are saved in the agent's folder (`photos/`, `screens/`) so you can
  see what it saw. Delete them there like any file.
- An answer you print becomes a PDF in your Documents/Datas folder first, like *Save as PDF*.
- The list of devices on your network is made by listening to what they announce and is
  shown, not stored.
- The address, user and password of your broker and the address and token of your Home
  Assistant are in `things.json` in Datas' data folder, readable only by your user. To make
  Datas forget one, save that connection with an empty address (or delete the file). *Erase
  everything* in Settings removes chats, notes and documents — not these, and not the keys of
  paid services.

## Images

Pictures are made on this computer by stable-diffusion.cpp. In Remember mode the result is saved
to `<data>/images/` (and can be deleted from the Images screen); in Forget mode it is shown once in
the window and never written to disk, and the engine's log is off. Prompts are not stored anywhere.
