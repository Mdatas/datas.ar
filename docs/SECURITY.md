# How Datas is protected

A plain account of what Datas does to keep the device and its owner safe, what it relies
on, and what it does **not** protect against. To report a problem, see
[SECURITY.md](../SECURITY.md) at the top of the repository.

## The shape of the app

Datas is a small program that listens on this computer only (`127.0.0.1:8420`) and a window
that talks to it. The AI engines (llama.cpp, whisper.cpp, stable-diffusion.cpp) are separate
programs started by Datas, also on `127.0.0.1`. Nothing is sent to the project: there is no
account, no usage statistics and no update check unless you press the button.

## The local service

A web page open in your browser can try to send requests to `127.0.0.1`. Three checks stop a
stranger's page from driving Datas (`local_only` in [`datas/server/app.py`](../datas/server/app.py)):

| Check | Stops |
|---|---|
| **Host** must be a local name (`127.0.0.1`, `localhost`, `::1`) | "DNS rebinding": a site that makes its own name point at your computer |
| **Origin / Sec-Fetch-Site** must be Datas' own window for anything that changes something | a page in your browser posting to Datas behind your back |
| **Content-Security-Policy** on the window: only Datas' own files, `script-src 'self'` | text from a web page or an AI answer running as a script in the window |

In the main window, answers from the AI and text from documents are turned into page
elements one piece at a time (`md()` in [`app.js`](../datas/server/ui/app.js)); they are never
inserted as markup. The agent's window escapes every text before showing it.

Programs that are not browser pages (scripts, other apps on this computer) can use the local
service freely — that is what the `/v1` address is for. Starting the service on the network
(`datas serve --host 0.0.0.0`) is a deliberate, advanced choice and is not needed for linking
devices.

## The internet, when you switch it on

When a chat or the agent may use the internet, every address is checked first
([`datas/netguard.py`](../datas/netguard.py)):

- only public addresses are opened; your router, printers, other computers and the computer
  itself are refused, including after a redirect, and the address actually connected to is
  checked again;
- Settings → Privacy → *Let the AI open addresses inside my own network* lifts this on purpose.

This matters because a web page can contain text written to trick an AI ("prompt
injection"). The AI reading a page should never become a way into your home network.

## Downloads

| What | Check |
|---|---|
| AI models | the size recorded in the catalog and the SHA-256 that Hugging Face publishes for the file; downloads resume where they stopped |
| llama.cpp engine | SHA-256 published with the release; the downloaded archive is deleted after unpacking |
| Datas installer (update) | size and SHA-256 published with the release, then the system's own installer is opened |
| ArtCraft Launcher | SHA-256 from the `SHA256SUMS.txt` published beside it |

A new engine version is installed **beside** the old one and tested before it is used; if it
fails, Datas goes back by itself. See [UPDATES.md](UPDATES.md).

Installers are **not yet code-signed**, so Windows SmartScreen and macOS Gatekeeper show a
warning on first start. Signing needs paid certificates and is on the roadmap.

## The agent

- Works only in its own folder plus the folders you tick for that session; the whole home
  folder or a disk root is refused.
- "Delete" moves to a trash folder inside the agent's folder.
- By default it asks before anything that writes in your folders, opens something, runs a
  program or uses a connection (MCP). Commands are off unless you switch them on.
- Running one of the programs found on the computer is not a way around those limits. While
  commands are off, `run_program` refuses the options that make a program run a script
  (Blender's `--python`, GIMP's `-b`, Pandoc's `--filter`, LibreOffice's `macro:` addresses,
  script files…), network addresses when internet is off or inside your own network, and
  files outside the folders you gave the agent. These checks read the arguments only and a
  list of known tricks is never complete — which is why running a program asks first.
- Tasks on a schedule run unattended: they do not ask. They are limited by the folders and
  the two switches (internet, commands) you set when you created the task, and by the checks
  above.
- A connection (MCP) **starts a program on your computer**. Datas lists only the ones you
  added and the ones offered by programs it found installed. Add only programs you trust.

Details: [AGENTS.md](AGENTS.md), [PROGRAMS.md](PROGRAMS.md).

## Your devices

Linked devices use TLS 1.3 with pinned certificates on both sides after a one-time pairing
code. Full description and limits: [DEVICES.md](DEVICES.md).

## What is stored, and how

- Settings, chats and notes are ordinary files in Datas' data folder, inside your own user
  folder. The settings file is readable only by your user account (mode 600 where the system
  supports it). None of it is encrypted on disk: someone with access to your unlocked user
  account can read it. Use your system's disk encryption (BitLocker, FileVault, LUKS) for that.
- Keys for paid services are in the same settings file. They are sent only to the service
  they belong to.
- Forget mode writes no chats, notes or logs.
- A damaged settings file is set aside and replaced with a working one; the previous copy is
  kept as a backup.

Details: [PRIVACY.md](PRIVACY.md).

## Checking a copy

`datas-cli selftest` checks that a copy of Datas is whole and behaves: the window files, the
lessons, writing and reading documents, an encrypted link between two test identities (and
the refusal of a third), and the two checks that keep other web pages out. It changes
nothing and downloads nothing. Every installer is built only if the finished app passes it.

## What Datas does not protect against

- Malware or another person already using your user account.
- A model file from an unknown source. Datas is neutral about what you load, and a model is
  data rather than a program, but it is read by the engine; prefer files from publishers you
  recognise.
- A paid online service you choose: it sees what you send it.
- The bigger creative tools (ComfyUI and others) and any program started through a
  connection: they run with your user's rights, like any program you install.
- Mistakes by the AI. An agent can still do the wrong thing inside the folders you allowed;
  that is why risky steps ask first and "delete" is a move to trash.
