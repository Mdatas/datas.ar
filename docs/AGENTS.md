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
| `list_dir(path)`, `find_files(pattern, path)` | list / search files | workspace + granted folders |
| `read_file(path)` | read text; PDF and .docx converted to text (200k chars cap) | same |
| `write_file(path, content)`, `make_dir(path)` | write text, create folders | same |
| `move_file(src, dst)`, `copy_file(src, dst)` | move/rename/copy; a destination ending in `/` is a folder | same |
| `delete_file(path)` | **never destroys**: moves to `<workspace>/_trash/<time>-<name>` | same; refuses to trash a granted folder itself |
| `open_path(target)` | open a file, folder or URL with the user's usual app | same (URLs need internet on) |
| `web_search(query)` | DuckDuckGo results: title, link, snippet | internet switch |
| `fetch_url(url)` | GET a page; HTML reduced to text (200k cap) | internet switch |
| `run_command(command)` | shell in the workspace, 60 s timeout | **off by default**; switch in the window / `--allow-shell` |

**Folders.** The agent always has its own workspace (`<data>/agent-workspace`). In the agent
window the user ticks which of their folders it may also use for this session — Desktop,
Documents, Downloads, Pictures, Music, Videos (found per OS: XDG on Linux, OneDrive-aware on
Windows) or any folder path typed in. The whole home folder or a disk root is refused on purpose.
Every tool resolves paths against that list; anything outside answers `DENIED`.

### Tasks it does by itself (scheduled)

`datas/agents/schedule.py`: tasks live in `<data>/agent/tasks.json` with a job text, a cadence
(`hour` / `day` / `week` + weekday / `once`), a time, the granted folders and the two switches.
A background thread in the server checks every 30 s and runs due tasks one at a time through the
same runner; a task missed while the computer was off runs at the next start. Each run writes
`<data>/agent/results/<task>-<time>.md` (summary + the list of tool calls), shown in the window's
inbox. They run while Datas is open — a tray/background service is roadmap 0.3.

### What "do tasks on my computer by itself" means today

Honest scope with the model sizes a normal laptop runs (4–14 B parameters): file and document
work (sort, rename, summarise, convert text), web research saved to files, scripts when
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

- **Script-driven app control, no vision** (reliable today): open apps and files, fill documents
  by writing the formats directly (.docx, .xlsx, .pdf), and drive programs through their own
  automation hooks — AppleScript/Shortcuts on macOS, PowerShell/COM on Windows (Office, Explorer),
  D-Bus/xdotool on Linux. Deterministic, loggable, undoable where the program allows.
- **"Look at my screen and help"**: a screenshot goes to the vision model, which explains what is
  on screen or what to click; the user clicks. Safe, useful, works on any device that runs a
  vision model.
- **Screen control, experimental, device-gated**: offered only where the Run screen's verdict is
  "yes" (a capable vision model on a real GPU), limited to one chosen window, with a dry-run
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

- Nothing runs on your machine unless you pass `--allow-shell`, and then each command is
  shown and confirmed unless you add `--yes`.
- Files are confined to the workspace directory you chose.
- Network access is on by default for `fetch_url` (reading pages); turn it off with
  `--no-network`. There is no tool that sends data anywhere.
- The model's claims are not trusted: the runner only reports tool results it actually
  observed, and the system prompt tells the model the same.
- A remote provider sees the task and tool results (that is what you asked for by
  selecting it). Use `local` for anything private.

## Roadmap for agents

- Scheduled/background agents with a result inbox in the UI.
- MCP client support so Datas agents can use MCP tool servers.
- Per-tool allowlists in config (e.g. shell allowed only for `git`, `pytest`).
