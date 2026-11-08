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
3. else stop and print the final answer (max 20 steps by default)

Events (`assistant`, `tool_call`, `tool_result`, `final`, `error`) stream to the CLI as
they happen.

### Tools

| Tool | Does | Gate |
|---|---|---|
| `list_dir(path)` | list files | workspace only |
| `read_file(path)` | read text (200k chars cap) | workspace only |
| `write_file(path, content)` | write text, creates folders | workspace only |
| `fetch_url(url)` | HTTP GET, text/JSON/XML bodies (200k cap) | on by default; `--no-network` |
| `run_command(command)` | shell in the workspace, 60 s timeout | **off by default**; `--allow-shell`, confirm per call unless `--yes` |

Workspace default: `~/.local/share/datas/agent-workspace`. Paths that escape it are
refused (`PermissionError` → the model sees "DENIED").

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
