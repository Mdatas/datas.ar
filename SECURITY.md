# Security

How Datas is protected, and what it does **not** protect against, is described in plain
words in **[docs/SECURITY.md](docs/SECURITY.md)**. Linked devices have their own page:
[docs/DEVICES.md](docs/DEVICES.md).

## In one paragraph

Datas runs on your device and listens on `127.0.0.1` only. There is no account, no usage
statistics, and nothing updates by itself. It downloads AI models from Hugging Face (checked
against the SHA-256 published there; a mismatch deletes the file), the llama.cpp engine from
its GitHub releases (a tested build, checked against the SHA-256 GitHub publishes with the
release when that can be read), and — only when you press the button — its own installer
(size and SHA-256 checked). Keys for paid services stay in the local settings file and are
sent only to the service they belong to. Devices you link talk over TLS 1.3 with a pinned
certificate on both sides.

## Things to know

- **The installers are not code-signed yet.** Windows and macOS warn on first start.
- **The data folder is not encrypted.** Someone using your unlocked user account can read
  your chats and settings. Use your system's disk encryption.
- **A model file is read by the engine.** Prefer files from publishers you recognise;
  engine updates bring upstream fixes (*Settings → Updates*).
- **The agent** works only in its own folder and the folders you tick, asks before risky
  steps, and runs commands only if you switch that on. A connection (MCP) or a "bigger
  creative tool" is a program running with your rights: add only what you trust.
- **`datas serve --host 0.0.0.0`** puts the window and the `/v1` address — and so the use of
  your paid keys — on your network, without a password. It is an expert option and is not
  needed for linking devices.
- **`datas pool worker --host <address>`** starts llama.cpp's own worker, which has no
  password and no encryption. Use linked devices instead (*Devices*), which wrap the same
  thing in an encrypted tunnel.
- **Cameras, printers, boards and your smart home** are used only when you ask, or when the
  agent asks you and you allow it. All of it is off for the agent until you switch it on for
  a task, and none of it can be reached from a linked phone or through another computer's
  window.
  → [docs/HARDWARE.md](docs/HARDWARE.md)

## Reporting a problem

Open an issue at <https://github.com/Mdatas/datas.ar/issues>, or — for something that should
not be public yet — use *Security → Report a vulnerability* on the repository page if it is
available, or write to the maintainer through the GitHub profile. Please include your system,
the Datas version (`datas-cli --version`) and the output of `datas-cli selftest` and
`datas-cli doctor` with any keys removed.
