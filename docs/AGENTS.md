# Agents

Datas lets the model *do* things — but only what you allow, inside a sandbox, with every
action visible.

## The built-in runner

```bash
datas agent "read all the .csv files in the workspace and write a summary to SUMMARY.md"
datas agent --allow-shell "clone https://github.com/… and run its tests"    # asks before each command
datas agent --allow-shell --yes "…"                                         # don't ask
datas agent --no-network "…"                                                # no fetch_url
datas agent --workspace ~/Projects/foo "…"                                  # sandbox elsewhere
```

`datas/agents/runner.py` is a plain tool-calling loop over the active provider's
`/v1/chat/completions` (local model, pool, or API key — identical code):

1. system prompt + task → model
2. if the reply contains `tool_calls`, run each tool, append results, go to 1
3. else stop and print the final answer (max 40 steps by default)

Events (`assistant`, `tool_call`, `tool_result`, `final`, `error`) stream to the CLI as
they happen.

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
| `run_command(command)` | a command in the agent's folder, 60 s at most | **off by default**; switch in the window / `--allow-shell` |
| `connection__function(…)` | functions offered by programs that speak the Model Context Protocol (MCP), such as the ArtCraft apps | always asks; see [PROGRAMS.md](PROGRAMS.md) |

**Folders.** The agent always has its own workspace (`<data>/agent-workspace`). In the agent
window the user ticks which of their folders it may also use for this session — Desktop,
Documents, Downloads, Pictures, Music, Videos (found per OS: XDG on Linux, OneDrive-aware on
Windows) or any folder path typed in. The whole home folder or a disk root is refused on purpose.
Every tool resolves paths against that list; anything outside answers `DENIED`.

### Approving actions — three levels

| Level | Asks before… | For whom |
|---|---|---|
| **Ask before risky actions** (default) | anything that writes, converts, moves, copies or trashes inside *your* folders, runs a command or a program, uses a connection (MCP), or opens a file or web address. Reading, searching and everything inside the agent's own folder (reversible via `_trash`) run freely. | everyone |
| **Ask before every action** | every single tool call, listings included | the first few runs, to see how it thinks |
| **Never — just do it** | nothing; a **Stop** button and the Esc key halt it at the next step | people watching the log |

Tasks on a schedule run with nobody watching, so they never ask; the folders and switches
chosen for the task are their limits.

The question appears as a card in the agent window (Allow / Deny / Allow everything for this
task); unanswered questions are denied after 15 minutes. Approving every click exists in every
serious agent product and is useful as a learning mode — but as a permanent setting it fails in
practice: after a dozen "OK"s people stop reading and rubber-stamp, which is less safe than a
good default. Hence the risk-based default plus a stop key.

### Tasks it does by itself (scheduled)

`datas/agents/schedule.py`: tasks live in `<data>/agent/tasks.json` with a job text, a cadence
(`hour` / `day` / `week` + weekday / `once`), a time, the granted folders and the two switches.
A background thread in the server checks every 30 s and runs due tasks one at a time through the
same runner; a task missed while the computer was off runs at the next start. Each run writes
`<data>/agent/results/<task>-<time>.md` (summary + the list of tool calls), shown in the window's
inbox. They run while Datas is open; running in the background with the window closed is on
the roadmap.

### What "do tasks on my computer by itself" means today

Honest scope with the AI sizes a normal laptop runs (4–14 billion parameters): file and
document work (sort, rename, summarise, write Word / Excel / PowerPoint / PDF files, convert
between formats with the programs installed), web research saved to files, scripts when
commands are allowed, and all of that on a schedule.

### Driving other programs (screen control) — planned, device-gated

Clicking around other programs is not ruled out; it is gated like everything else, by what the
device can carry, and it comes after images. Why it is not in the first version:

1. **Reliability.** Screen control means: screenshot → a vision model finds the button → click
   at coordinates → screenshot again → verify → repeat. Every step can go wrong, and even the
   best paid models fail a large share of such tasks; the small local models that fit a normal
   laptop fail far more often.
2. **Speed.** Each step pushes a screenshot through a vision model. On a CPU-only laptop that is
   tens of seconds per step; a 20-step task becomes many minutes, and when it derails you only
   find out at the end.
3. **Reversibility.** A trashed file comes back; a click that sends an email, confirms a payment
   or deletes something in another program does not. Datas cannot undo other programs.
4. **Exposure.** The model sees the whole screen — other windows, passwords, banking — and text
   on screen can carry instructions that hijack it (prompt injection).

What will ship, in this order:

- **Program control without looking at the screen** — *partly shipped*: the agent opens
  programs and files, writes documents in their own formats (.docx, .xlsx, .pptx, .pdf),
  converts with the programs it finds, and uses the functions a program offers through MCP
  ([PROGRAMS.md](PROGRAMS.md)). Still to come: the system's own automation hooks —
  AppleScript/Shortcuts on macOS, PowerShell/COM on Windows (Office, Explorer),
  D-Bus/xdotool on Linux. Deterministic, loggable, undoable where the program allows.
- **"Look at my screen and help"**: a screenshot goes to the vision model, which explains what is
  on screen or what to click; the user clicks. Safe, useful, works on any device that runs a
  vision model.
- **Screen control, experimental, device-gated**: offered only where *What this device can do*
  says "yes" (a capable vision model on a real GPU), limited to one chosen window, with a dry-run
  mode, confirm-before-click, a visible cursor and a panic key (Esc) that stops it. Off by
  default; the abilities panel reports "Screen control: yes / slow / no" like every other ability.

### Planned: the agent's own browser

For sites that need JavaScript, forms or a login, the plan is a browser that belongs to the
agent — Playwright's bundled **Firefox** (Mozilla's open-source build, downloaded on first use,
~90 MB), isolated profile, no sign-ins, no telemetry, tracker blocking and fingerprint
resistance on, wiped per session in Forget mode; optional Tor routing with the warning that it
is slower and some sites refuse it. Off by default behind one switch. The user's own browser is
never driven. Without Tor a website still sees the home IP address, exactly as when the user
browses — no add-on changes that.

### Which models can do this

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
- **Internet** is a switch per session. With it on, the agent can search and read pages; it
  cannot open addresses inside your own network unless you allow that in Settings. Text on a
  web page can be written to mislead an AI ("prompt injection") — one more reason risky
  steps ask first.
- **The AI's claims are not trusted.** The runner reports only the tool results it actually
  observed, and tells the AI so.
- **A paid online service sees the task and the tool results** — that is what choosing it
  means. Use an AI on this device for anything private.

The full picture, including what Datas does *not* protect against: [SECURITY.md](SECURITY.md).

## Roadmap for agents

- [x] Scheduled tasks with a results inbox in the window.
- [x] MCP client: the agent uses the functions of programs that speak MCP.
- [x] Open programs found on the computer (LibreOffice, FFmpeg, Inkscape, Blender, ArtCraft…).
- [ ] The agent's own browser (above).
- [ ] The system's automation hooks; "look at my screen and help"; screen control (above).
- [ ] Per-tool allowlists in the settings (for example commands allowed only for `git` and
      `pytest`), and a kept record of every tool call.
- [ ] Running scheduled tasks with the window closed.
