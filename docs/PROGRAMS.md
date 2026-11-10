# Working with other programs: programs found, connections (MCP), ArtCraft

Datas does not try to be an office suite or an image editor. It lets the AI **use the open
programs you already have**, and tells you which ones it found.

## Programs found on this computer

On the Tools screen, *Programs on this computer* lists what Datas found by looking in the
usual places (the system's program list and standard install folders):

| Kind | Programs looked for |
|---|---|
| Office and documents | LibreOffice, Pandoc, Tesseract (text recognition) |
| Sound and video | FFmpeg (if none is installed, Datas can fetch a copy for its own use) |
| Pictures and design | ImageMagick, Inkscape, GIMP, Krita |
| 3D and technical drawing | Blender, OpenSCAD, FreeCAD |
| ArtCraft | the Craft apps (see below) |
| Yours | anything you list in `<data folder>/programs.json` |

What the agent can do with them (it asks first, by default):

| Agent tool | Does |
|---|---|
| `read_file` | reads PDF, Word, Excel, PowerPoint, web pages and text |
| `save_document` | writes an answer as Word, Excel, PowerPoint, PDF, HTML, Markdown or text |
| `convert_file` | converts between formats using the best program found (for example .docx → .pdf with LibreOffice, .mp4 → .mp3 with FFmpeg, .svg → .png with Inkscape) |
| `list_programs` | tells the AI which programs are available |
| `run_program` | runs one of the **found** programs with the arguments the AI gives, starting in the agent's own folder |
| `open_path` | opens a file or folder with a chosen program, for you to continue by hand |

`run_program` only starts programs from the list above; it is not a general command line.
That stays behind its own switch in the agent window (*May run commands*). While that switch
is off, a found program is for opening, converting and exporting — so `run_program`:

- **asks first**, unless you chose *Never ask* for that task (tasks on a schedule run
  unattended and do not ask): you see the program and the exact arguments before it starts;
- **refuses what would make a program run a script or start another program**: Blender's
  `--python`, GIMP's `-b`, Pandoc's `--filter` and `--pdf-engine`, LibreOffice's `macro:`
  addresses, files of arguments (`@file`), and script files (`.py`, `.sh`, `.bat`, `.ps1`…);
- **follows the internet switch**: a web or network address in the arguments is refused when
  internet is off for that session, and an address inside your own network is refused unless
  you allowed those in Settings;
- **keeps to your folders**: an argument that names a file or folder outside the agent's
  folder and the ones you ticked is refused.

These checks read the arguments; they cannot see what a program does once it runs, and a
list of known tricks is never complete. That is why the question stays on by default. With
*May run commands* on, none of this applies — you have then allowed any command.

Programs you list yourself in `programs.json` are not filtered: you decided what they are.

## Connections (Model Context Protocol)

The **Model Context Protocol (MCP)** is an open standard that lets a program offer its
functions to an AI in a common way. Datas' agent is an MCP *client*: at the start of a task
it starts each connection, asks which functions it offers, and makes them available to the
AI as tools named `connection__function`. Every such tool asks before it runs.

- *Tools → Connections* lists them, with **Test** (start it, list its functions, stop it).
- Connections come from programs Datas found that offer one, and from the ones you add by
  hand: a name, the program to start and its extra words. They are kept in
  `<data folder>/mcp.json`, in the same shape other MCP clients use (`mcpServers`). `{root}`
  in an argument is replaced by the agent's folder.
- Datas speaks MCP over standard input/output (protocol version `2025-06-18`).

**A connection starts a program on your computer with your rights.** Add only programs you
trust.

## ArtCraft

[ArtCraft](https://getartcraft.com/) is an open suite of creative desktop apps (its site
lists sixteen "Crafting Apps": PhotoCraft, VectorCraft, FilmCraft, LightCraft, PdfCraft,
EffectCraft, DesignCraft, FigCraft, TextureCraft, MaterialCraft, WordCraft, SoundCraft,
DeckCraft, CADCraft, GridCraft and Craft Anything), under the MIT or Apache-2.0 licences. Its
site states that every app can be driven from a command line, a JSON control channel or an
MCP server — which is exactly what an agent needs.

What Datas does:

- **Get ArtCraft** downloads the ArtCraft Launcher for your system from the project's own
  releases, checks it against the published `SHA256SUMS.txt`, and opens the installer. The
  launcher then installs and updates the apps you choose.
- Installed Craft apps are found like any other program, and each one whose command-line
  tool is present is offered as a **connection** automatically.

What was verified, and what was not:

| | Status |
|---|---|
| App list, licences, "CLI / JSON / MCP" claim | read on getartcraft.com |
| Launcher file names and checksums file | read from the launcher's releases |
| PdfCraft's commands (`pdfcraft-cli mcp --root <folder>`) | read from the documentation shipped in the PdfCraft 0.19.0 release |
| The other apps' commands | **assumed** to follow the same pattern; marked as unverified in the list |
| Running the real apps through Datas | **not tested** in the development environment; the MCP client itself is tested against a stand-in server (`tests/fake_mcp_server.py`) |

If a Craft app does not answer **Test**, add it by hand with the command its own
documentation gives.

Code: [`datas/programs.py`](../datas/programs.py), [`datas/mcp.py`](../datas/mcp.py),
[`datas/agents/tools.py`](../datas/agents/tools.py). Tests: `tests/test_programs.py`.
