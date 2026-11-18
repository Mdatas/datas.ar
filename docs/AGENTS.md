# The AI acting for you (the agent)

Datas lets the AI *do* things — but only what you allow, inside a sandbox, with every
action visible.

## In the chat: one box, one conversation

There is no separate place to give the AI a task. In any chat, the button at the top
(**Only talks** / **Can act (n)**) says what the AI may do in that chat:

- **Work with files** — its own folder, plus the folders you tick (Desktop, Documents…);
- **Its own terminal** — PowerShell on Windows, bash on Mac and Linux;
- **Its own browser** — a separate, visible window (needs Internet on for the chat);
- **Configure this computer** — open apps and settings, change a few settings, with undo;
- **Devices around this computer** — camera, printer, boards, home and industrial devices;
  and **Mouse and keyboard** (experimental) under it;
- **Ask me before** — anything risky (default), every step, or never.

All off, the AI only answers. With any on, the same chat runs the agent: the whole
conversation (your notes, documents, helper and earlier messages) is what the AI works from;
its steps appear inside the answer; a question ("Run the command: mkdir PDFs") appears as a
card with **Allow** / **Don't**; **Stop** stops it; and under the answer Datas writes what the
tools themselves reported — *Checked: 3 actions done; 1 did not work: …* — never just what the
AI says. Code: `ChatBody.hands` and `_chat_with_hands` in `datas/server/app.py`,
`AgentConfig.conversation` in `datas/agents/runner.py`, `Chat.handsDialog` / `addStep` /
`pollAsks` / `reallyNode` in `datas/server/ui/chat.js`.

The separate agent window stays for **tasks on a schedule** (below), which run with nobody
watching. From a linked phone, the terminal, the browser, configuring the computer and its
devices are refused.

## The built-in runner

```bash
datas agent "read all the .csv files in the workspace and write a summary to SUMMARY.md"
datas agent --allow-shell "clone https://github.com/… and run its tests"    # asks before each command
datas agent --allow-shell --yes "…"                                         # don't ask
datas agent --no-network "…"                                                # no fetch_url
datas agent --workspace ~/Projects/foo "…"                                  # sandbox elsewhere
datas agent --devices "take a photo and tell me what plant this is"         # camera, printer, boards…
datas agent --devices --control "…"                                         # + mouse and keyboard (experimental)
```

`datas/agents/runner.py` is a plain tool-calling loop over the active provider's
`/v1/chat/completions` (the AI on this device or on another of your devices — identical code):

1. system prompt + task → model
2. if the reply contains `tool_calls`, run each tool, append results, go to 1
3. else stop and print the final answer (max 40 steps by default)

Events (`assistant`, `tool_call`, `tool_result`, `picture`, `final`, `error`) stream to the
CLI and to the agent window as they happen. A `picture` is a photo or a picture of the screen
that a tool took: the window shows it, and an AI that understands pictures receives it.

### Tools

| Tool | Does | Gate |
|---|---|---|
| `list_dir(path)`, `find_files(pattern, path)` | list / search files | the agent's folder + the folders you ticked |
| `read_file(path)` | read text; PDF, Word, Excel, PowerPoint and web pages are turned into text (200k characters at most) | same |
| `write_file(path, content)`, `make_dir(path)` | write text, create folders | same |
| `save_document(path, content)` | write Markdown `content` as a Word, Excel, PowerPoint, PDF, web page, Markdown or text file; the ending of the name picks the format | same |
| `convert_file(source, to)` | convert between formats with the best program found (.docx → .pdf, .svg → .png, .mp4 → .mp3…) | same |
| `move_file(src, dst)`, `copy_file(src, dst)` | move, rename, copy; a destination ending in `/` is a folder | same |
| `delete_file(path)` | **never destroys**: moves to `<agent folder>/_trash/<time>-<name>` | same; refuses to trash a ticked folder itself |
| `list_programs()` | which open programs were found on this computer and what each is for | — |
| `run_program(program, arguments)` | run one of those programs | asks first; while commands are off it refuses script-running options, network addresses when internet is off, and files outside your folders — see [PROGRAMS.md](PROGRAMS.md) |
| `open_path(target, program?)` | open a file, folder or web address with your usual program, or with a chosen one | asks; web addresses need internet on |
| `web_search(query)` | DuckDuckGo results: title, link, snippet | internet switch |
| `fetch_url(url)` | read a page; HTML reduced to text (200k at most); addresses inside your own network are refused | internet switch |
| `run_command(command, timeout)` | the agent's own terminal: a real shell (PowerShell on Windows, bash elsewhere) with pipes, redirection and variables; starts in the agent's folder and remembers `cd`; 60 s unless the AI asks for more (900 at most) | **off by default**; switch in the window / `--allow-shell`; asks before each command |
| `browser_open(url)`, `browser_read()`, `browser_click(n)`, `browser_type(n, text, submit)`, `browser_back()` | the agent's own browser window (below): pages that need JavaScript, forms, clicking through | its own switch **and** internet; clicking and typing ask; never types into a password field |
| `connection__function(…)` | functions offered by programs that speak the Model Context Protocol (MCP), such as the ArtCraft apps | always asks; see [PROGRAMS.md](PROGRAMS.md) |
| `list_devices()`, `network_devices()` | what is plugged into this computer; what announces itself on the network | hardware switch |
| `take_photo()`, `look_at_screen()` | one picture from a camera / of the screen, saved in the agent's folder and shown to an AI that understands pictures | hardware switch; asks |
| `print_file(path)` | print a file on paper | hardware switch; asks |
| `serial_read(port)`, `serial_send(port, text)` | listen to / write a line to a board or instrument (Arduino, ESP32, 3D printer) | hardware switch; writing asks |
| `mqtt_read(topic)`, `mqtt_publish(topic, message)` | smart-home messages through your own broker | hardware switch; sending asks |
| `home_list(domain)`, `home_do(service, entity)` | what your Home Assistant knows; ask it to do something | hardware switch; doing asks |
| `modbus_read(…)`, `modbus_write(…)` | values of industrial devices (PLC, inverter, meter) | hardware switch; writing asks |
| `mouse_keyboard(action, …)` | move, click, type, press keys (experimental) | its own switch on top; every action asks |
| `list_apps(search)` | the apps installed on this computer (Start menu on Windows, Applications on macOS, the app menu on Linux) | **Configure this computer** switch |
| `open_app(name)` | open one of them | same; asks |
| `open_settings(page)` | open a page of the system settings: display, sound, Bluetooth, Wi-Fi, printers, mouse, keyboard, default apps, apps, start-up apps, accounts, sign-in options, date and time, language, privacy, updates, power, notifications, colours, background, backup | same; asks |
| `pc_settings()`, `change_pc_setting(name, on)` | read / change a short list of everyday settings: dark mode, file name endings, hidden files, taskbar on the left (Windows 11). Per user, no administrator rights; the earlier value is kept | same; changing asks |
| `undo_pc_changes()` | put every setting the agent changed back | same; asks |
| `sign_in_by_you(app, account)` | open the app and wait while **you** sign in | same; it always waits for you |

The hardware tools are explained for everyone in [HARDWARE.md](HARDWARE.md).

**Folders.** The agent always has its own workspace (`<data>/agent-workspace`). In the agent
window the user ticks which of their folders it may also use for this session — Desktop,
Documents, Downloads, Pictures, Music, Videos (found per OS: XDG on Linux, OneDrive-aware on
Windows) or any folder path typed in. The whole home folder or a disk root is refused on purpose.
Every tool resolves paths against that list; anything outside answers `DENIED`.

### Approving actions — three levels

| Level | Asks before… | For whom |
|---|---|---|
| **Ask before risky actions** (default) | anything that writes, converts, moves, copies or trashes inside *your* folders, runs a command or a program, uses a connection (MCP), opens a file or web address, or uses hardware in a way that looks at you or acts on the world (a photo, a picture of the screen, printing, writing to a board, switching something, the mouse and keyboard). Reading, searching, listing devices, reading sensors and everything inside the agent's own folder (reversible via `_trash`) run freely. | everyone |
| **Ask before every action** | every single tool call, listings included | the first few runs, to see how it thinks |
| **Never — just do it** | nothing; a **Stop** button and the Esc key halt it at the next step | people watching the log |

Tasks on a schedule run with nobody watching, so they never ask; the folders and switches
chosen for the task are their limits.

The question appears as a card in the agent window (Allow / Deny / Allow everything for this
task); unanswered questions are denied after 15 minutes. For hardware the question is in
plain words and in your language — *Print report.pdf on paper (2 copies)*, *Ask Home Assistant
to do light.turn_on on light.kitchen* — instead of the tool's name and raw arguments.

Approving every click exists in every serious agent product and is useful as a learning mode
— but as a permanent setting it fails in practice: after a dozen "OK"s people stop reading
and rubber-stamp, which is less safe than a good default. Hence the risk-based default plus a
stop key.

### Configure my PC

The **Configure my PC** button in the agent window switches on *May configure this computer*
and starts the task with "Configure my PC: ". Ask, for example: *open Outlook, Spotify and
WhatsApp so I can sign in*, *dark mode and show file endings*, *open the printer settings*.

- **Sign-ins are yours.** The agent never asks for, reads, stores or types a password, code
  or card number. It opens the app and shows a card: "Please sign in to Spotify yourself…";
  you type, then press Allow (done) or Deny (skip). A password given to an AI would stay in
  its conversation and logs, and text on screen can try to mislead it.
- **Only listed settings are changed directly** (`datas/agents/pc_tools.py`, `SETTINGS`): per
  user, reversible, the earlier value kept in `<data>/agent/pc-changes.json`; *undo* puts all
  back. Anything else: the agent opens the right page of the settings, and you change it — or,
  with the mouse-and-keyboard switch, it does it on screen, asking before every click.
- **Not for tasks that run by themselves**, and not from a linked phone.
- macOS: System Settings has no stable public address per page, so it opens at the start and
  the agent says where to look. Linux: GNOME Settings panels.

### Tasks it does by itself (scheduled)

`datas/agents/schedule.py`: tasks live in `<data>/agent/tasks.json` with a job text, a cadence
(`hour` / `day` / `week` + weekday / `once`), a time, the granted folders and three switches
(internet, commands, hardware — never the mouse and keyboard).
A background thread in the server checks every 30 s and runs due tasks one at a time through the
same runner; a task missed while the computer was off runs at the next start. Each run writes
`<data>/agent/results/<task>-<time>.md` (summary + the list of tool calls), shown in the window's
inbox. They run while Datas is running: with its window open, or — with *Start Datas with the
computer* on (Settings, or the button in the agent window) — in the background on Windows, macOS
and Linux. Closing the window then hands the tasks to a background Datas at once
(`service.continue_in_background`, `datas-cli serve --wait-free`), not only at the next login.
From the command line: `datas-cli service install` ([DEVICES.md](DEVICES.md)).

### What "do tasks on my computer by itself" means today

Honest scope with the AI sizes a normal laptop runs (4–14 billion parameters): file and
document work (sort, rename, summarise, write Word / Excel / PowerPoint / PDF files, convert
between formats with the programs installed), web research saved to files, scripts when
commands are allowed, simple hardware jobs when that switch is on (a photo, a printout, a
reading from a board or a sensor, switching a light through your hub), and all of that on a
schedule.

### Looking at the screen and driving other programs — experimental, behind its own switch

Two things exist today:

- **"Look at my screen and help"** — in a chat, the camera button → *A picture of my screen*
  attaches what is on the screen to your question; the AI explains it or says what to click,
  and you click. Safe, and it works with any AI that understands pictures.
- **Mouse and keyboard** — with the agent's second switch on, the agent looks at the screen
  (`look_at_screen`) and then moves, clicks, types and presses keys (`mouse_keyboard`).

The second one is experimental and guarded, for four reasons that have not gone away:

1. **Reliability.** Screen control means: picture of the screen → the AI finds the button →
   click at that place → picture again → check → repeat. Every step can go wrong, and even
   the best paid models fail a large share of such tasks; the small AIs that fit a normal
   laptop fail far more often.
2. **Speed.** Each step pushes a picture through the AI. On a laptop without a graphics card
   that is tens of seconds per step; a 20-step task becomes many minutes.
3. **Reversibility.** A trashed file comes back; a click that sends an email, confirms a
   payment or deletes something in another program does not. Datas cannot undo other programs.
4. **Exposure.** The AI sees the whole screen — other windows, passwords, banking — and text
   on screen can carry instructions meant to mislead it (prompt injection).

So: its own switch, off for every new task; every action asks first unless you chose *never*;
the agent must look before it may click, and can only click inside the picture it was shown
(its positions are converted to the mouse's own, also on screens that count dots differently);
**moving the mouse into a corner of the screen stops it at once**; it is never available to a
task that runs by itself, nor from a linked phone. It is not held back on weaker devices —
Datas says plainly where it cannot work (Linux with Wayland) and leaves the choice to you.

Still to come:

- **Program control without looking at the screen** — *partly there*: the agent opens
  programs and files, writes documents in their own formats (.docx, .xlsx, .pptx, .pdf),
  converts with the programs it finds, and uses the functions a program offers through MCP
  ([PROGRAMS.md](PROGRAMS.md)). Not yet: the system's own automation hooks —
  AppleScript/Shortcuts on macOS, PowerShell/COM on Windows (Office, Explorer),
  D-Bus/xdotool on Linux. Deterministic, loggable, undoable where the program allows.
- For the mouse and keyboard: limiting it to one chosen window, a dry-run mode that only says
  what it would do, and a visible marker where it is about to click.

### The agent's own browser

`datas/agents/browser.py`. For sites that need JavaScript, forms or clicking through, the agent
opens **a separate browser window of its own**: a copy of Edge, Chrome, Chromium or Brave found
on the computer (nothing is downloaded), started with its own empty profile in
`<data>/agent/browser` — never the person's browser, sign-ins, cookies or history. It is driven
through the browser's built-in debugging interface (Chrome DevTools Protocol) over a local
connection.

- **Visible.** The window is on screen: the person watches every step and can take over. On a
  computer with no screen (a Raspberry Pi or server) it runs without a window.
- **Passwords are typed by the person**, in that window; the agent refuses to type into a
  password field.
- **Pages are text plus numbered elements** — `[3] button: Send` — so even small AIs can act.
- **Internet must be on**, and the browser switch too. Addresses inside the person's own network
  are refused (also after a click leads there) unless allowed in Settings.
- **Clicking and typing ask first** under the default approval level; reading does not.
- The window closes with the task; in Forget mode its profile is wiped.

### Which models can do this

Measured, not guessed: `scripts/e2e_real.py --agent` gives the agent five real tasks (write a
file, rename it, make a folder and move it there, write a Word document, read a file and write
what it says) and checks the result **on disk**. November 2026, on GitHub's computers:

| AI | Linux | Windows |
|---|---|---|
| Qwen3 0.6B (the one shipped inside Datas) | 4 of 5 | 1 of 5 — and it said "done" when it was not |
| Qwen3 4B | 5 of 5 | 5 of 5 |

So the agent window warns when the running AI is under 3 billion parameters and names one
that fits the device, and after every task it lists what the tools *really* did — from their
own answers, not from the AI's summary.

When the engine cannot write an AI's own tool format — for example Gemma 4 on llama.cpp
answers "map: filter-mapping not implemented" (llama.cpp issue #21547) — the agent, and a chat
with internet on, switch by themselves to describing the tools in plain text and reading the
AI's `<tool_call>{…}</tool_call>` replies. Slower and a little less reliable, but it works with
any AI.

Tool calling needs a model whose chat template emits tool calls and a llama-server
started with `--jinja` (Datas always does). In the catalog, every entry with `tools` in
`capabilities` is suitable; the stronger the model, the more reliably it plans. On small
devices Qwen3 4B / Gemma 4 E4B manage simple file tasks; gpt-oss, Qwen3.8 27B and the
MoE 30B-class models are the ones to use for multi-step work.

## Bring your own framework

Because every provider is exposed at `http://127.0.0.1:8420/v1`, any agent framework that
speaks the OpenAI API works unchanged:

```python
# smolagents / openai SDK / LangGraph / your own
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8420/v1", api_key="not-needed")
client.chat.completions.create(model="datas", messages=[...], tools=[...])
```

Open Interpreter, Aider, Continue, Cline and similar tools accept a custom base URL in
their settings; point them at the same address.

## Safety model, stated plainly

- **Folders.** The agent works in its own folder and in the folders you tick for that
  session. Every file tool checks every path; anything else answers `DENIED`. The whole home
  folder or a disk root cannot be ticked.
- **Nothing is destroyed.** "Delete" moves to the agent's trash folder.
- **Commands are off** unless you switch them on (`--allow-shell`), and then each one is
  shown and asked about unless you chose *Never ask* (`--yes`).
- **Programs and connections ask first.** A program started with `run_program`, or a
  function of a connection (MCP), runs with your user's rights — the question shows exactly
  what will run. While commands are off, `run_program` also refuses script-running options,
  network addresses when internet is off, and files outside your folders. A connection is a
  program you added yourself: Datas cannot see inside it.
- **Tasks on a schedule do not ask** — nobody is there to answer. They are bound by the
  folders and the switches you chose for the task.
- **Hardware is off** unless you switch it on for the task, and what looks at you or acts
  on the world asks first: a photo, a picture of the screen, printing, writing to a board,
  switching something at home, writing to a machine. The mouse and keyboard have a second
  switch, ask before every action, and stop when the mouse reaches a corner of the screen.
  None of it can be reached from a linked phone. Details: [HARDWARE.md](HARDWARE.md).
- **Internet** is a switch per session. With it on, the agent can search and read pages; it
  cannot open addresses inside your own network unless you allow that in Settings. Text on a
  web page can be written to mislead an AI ("prompt injection") — one more reason risky
  steps ask first.
- **The AI's claims are not trusted.** The runner reports only the tool results it actually
  observed, and tells the AI so.

The full picture, including what Datas does *not* protect against: [SECURITY.md](SECURITY.md).

## Roadmap for agents

- [x] Scheduled tasks with a results inbox in the window.
- [x] MCP client: the agent uses the functions of programs that speak MCP.
- [x] Open programs found on the computer (LibreOffice, FFmpeg, Inkscape, Blender, ArtCraft…).
- [x] Hardware: camera, screen, printer, boards on serial ports, MQTT, Home Assistant,
      Modbus, devices on the network ([HARDWARE.md](HARDWARE.md)).
- [x] "Look at my screen and help" (chat); mouse and keyboard, experimental (agent).
- [x] The agent's own browser (above), and its own terminal: a real shell that remembers `cd`.
- [ ] The system's automation hooks; one-window limit and dry run for the mouse and keyboard.
- [ ] Per-tool allowlists in the settings (for example commands allowed only for `git` and
      `pytest`), and a kept record of every tool call.
- [x] Running scheduled tasks with the window closed — Windows, macOS and Linux, with the
      background service; closing the window hands over at once.
