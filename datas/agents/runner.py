"""Tool-calling agent loop over any OpenAI-compatible endpoint."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from datas.agents import tools as T
from datas.config import agent_workspace

SYSTEM = (
    "You are an agent running locally on the user's own computer through Datas.ar. "
    "You can call tools to list, find, read, write, move, copy and (reversibly) delete files, open "
    "files or folders for the user{shell}{net}. Folders you may use: {roots}. "
    "Paths may be absolute inside those folders or relative to your workspace ({workspace}). "
    "Documents: read_file understands PDF, Word, Excel and PowerPoint; save_document writes "
    "Word (.docx), Excel (.xlsx), PowerPoint (.pptx) and PDF files from Markdown; convert_file "
    "changes a file's format; list_programs shows the programs installed here that you can run "
    "or open files in{mcp}.{things} "
    "Work step by step: decide, call a tool, read the result, continue. Prefer moving files into "
    "clearly named folders over deleting; never delete what you were not asked to. "
    "When the task is complete, answer with a short summary of what you did and where the results are, "
    "in the user's language. Never claim to have done something a tool result does not confirm."
)


@dataclass
class AgentConfig:
    base_url: str = "http://127.0.0.1:8420/v1"
    api_key: str = ""
    model: str = "datas"
    workspace: Path = field(default_factory=agent_workspace)
    roots: list[Path] = field(default_factory=list)  # user-granted folders (Documents, Downloads…)
    allow_shell: bool = False
    allow_network: bool = True
    max_steps: int = 40
    temperature: float = 0.2
    ask: str = "risky"  # all | risky | none
    confirm: Callable[[str], bool] | None = None
    should_stop: Callable[[], bool] | None = None
    lang: str = "en"
    allow_local: bool = False  # web tools may open addresses inside the user's own network
    use_programs: bool = True  # connect the programs that offer their own tools (MCP)
    allow_things: bool = False  # cameras, printers, boards, home and industrial devices
    allow_control: bool = False  # the mouse and keyboard (experimental)
    allow_setup: bool = False  # "configure my PC": apps, settings pages, a few settings
    sign_in_wait: Callable[[str], bool] | None = None  # waits while the person signs in
    vision: bool = False  # the AI understands pictures: photos and screen pictures are shown to it


def run_agent(task: str, cfg: AgentConfig) -> Iterator[dict]:
    """Yield events: {'type': 'assistant'|'tool_call'|'tool_result'|'picture'|'final'|'error',
    ...}. A 'picture' is a photo or a picture of the screen a tool took, as a data: address."""
    ctx = T.ToolContext(
        workspace=cfg.workspace,
        roots=[Path(r) for r in cfg.roots],
        allow_shell=cfg.allow_shell,
        allow_network=cfg.allow_network,
        allow_local=cfg.allow_local,
        ask=cfg.ask,
        confirm=cfg.confirm,
        should_stop=cfg.should_stop,
        lang=cfg.lang,
        allow_things=cfg.allow_things,
        allow_control=cfg.allow_things and cfg.allow_control,
        vision=cfg.vision,
        allow_setup=cfg.allow_setup,
        sign_in_wait=cfg.sign_in_wait or cfg.confirm,
    )
    cfg.workspace.mkdir(parents=True, exist_ok=True)
    session = None
    if cfg.use_programs:
        try:
            from datas import mcp

            session = mcp.Session(Path(cfg.roots[0]) if cfg.roots else cfg.workspace)
            if session.specs:
                session.start_all()
                for name, err in session.errors.items():
                    yield {
                        "type": "assistant",
                        "step": 0,
                        "content": f"({name} is not available: {err})",
                    }
                ctx.mcp = session if session.index else None
        except Exception as e:  # noqa: BLE001 - optional extra, never a reason to fail the task
            yield {
                "type": "assistant",
                "step": 0,
                "content": f"(programs with their own tools were skipped: {e})",
            }
    try:
        yield from _loop(task, cfg, ctx)
    finally:
        if session is not None:
            session.stop()


def _loop(task: str, cfg: AgentConfig, ctx: T.ToolContext) -> Iterator[dict]:
    sys_msg = SYSTEM.format(
        shell=", run shell commands" if cfg.allow_shell else "",
        net=", search the web and open web pages" if cfg.allow_network else "",
        roots="; ".join(str(r) for r in ctx.all_roots()),
        workspace=cfg.workspace,
        mcp=(
            "; tools whose name starts with a program's name (for example pdfcraft__…) work "
            "inside that program"
            if ctx.mcp is not None
            else ""
        ),
        things=(
            " The user also let you use the devices around this computer: list_devices shows "
            "cameras, screens, printers, boards on serial ports and the home or industrial "
            "connections that are set up; network_devices shows what is on the network. "
            "Anything that acts on the real world (printing, writing to a board, switching "
            "something, the mouse and keyboard) cannot be undone: do exactly what was asked, "
            "one step at a time, and say what happened."
            if ctx.allow_things
            else ""
        )
        + (T.pc_tools.SYSTEM_HINT if ctx.allow_setup else ""),
    )
    messages: list[dict] = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": task},
    ]
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    local = cfg.base_url.startswith(("http://127.0.0.1", "http://localhost"))
    written = False  # tools described in the text instead of the AI's own tool format
    with httpx.Client(timeout=httpx.Timeout(600, connect=30), trust_env=not local) as client:
        step = -1
        while step + 1 < cfg.max_steps:
            step += 1
            if cfg.should_stop and cfg.should_stop():
                yield {
                    "type": "error",
                    "step": step,
                    "error": "stopped by user",
                    "events": ctx.events,
                }
                return
            if written:
                payload = {
                    "model": cfg.model,
                    "messages": written_messages(messages, T.schemas(ctx)),
                    "temperature": cfg.temperature,
                }
            else:
                payload = {
                    "model": cfg.model,
                    "messages": messages,
                    "tools": T.schemas(ctx),
                    "tool_choice": "auto",
                    "temperature": cfg.temperature,
                }
            try:
                r = client.post(f"{cfg.base_url}/chat/completions", json=payload, headers=headers)
                if r.status_code >= 400 and not written and template_trouble(r.text):
                    # the engine cannot write this AI's own tool format (for example Gemma 4 on
                    # llama.cpp: "map: filter-mapping not implemented"): describe the tools in
                    # plain text instead, which every AI can follow, and try the step again
                    written = True
                    yield {
                        "type": "assistant",
                        "step": step,
                        "content": "(This AI's own tool format is not supported by the engine; "
                        "the agent describes its tools in plain text instead.)",
                    }
                    step -= 1
                    continue
                if r.status_code >= 400:
                    yield {
                        "type": "error",
                        "step": step,
                        "error": f"HTTP {r.status_code} from {cfg.base_url}: {r.text[:400]}",
                    }
                    return
                msg = r.json()["choices"][0]["message"]
            except (httpx.HTTPError, KeyError, ValueError) as e:
                yield {"type": "error", "step": step, "error": str(e)}
                return
            calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if written and not calls:
                calls, content = read_written_calls(content)
            messages.append(
                {"role": "assistant", "content": content, "tool_calls": calls}
                if calls
                else {"role": "assistant", "content": content}
            )
            if content:
                yield {"type": "assistant", "step": step, "content": content}
            if not calls:
                yield {"type": "final", "step": step, "content": content, "events": ctx.events}
                return
            for c in calls:
                fn = c.get("function", {})
                name, args = fn.get("name", ""), fn.get("arguments", "{}")
                yield {"type": "tool_call", "step": step, "name": name, "arguments": args}
                result = T.call(ctx, name, args)
                yield {"type": "tool_result", "step": step, "name": name, "result": result[:4000]}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.get("id", name),
                        "name": name,
                        "content": result,
                    }
                )
            # pictures the tools took (camera, screen): shown to an AI that can see, after
            # all the tool answers of this step — and to the person, in the agent's window
            if ctx.images:
                _forget_old_pictures(messages, keep=KEEP_PICTURES - len(ctx.images))
            for pic in ctx.images:
                url = "data:image/jpeg;base64," + base64.b64encode(pic["jpeg"]).decode()
                yield {"type": "picture", "step": step, "name": pic["name"], "url": url}
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"This is the picture {pic['name']}."},
                            {"type": "image_url", "image_url": {"url": url}},
                        ],
                    }
                )
            ctx.images.clear()
        yield {
            "type": "error",
            "step": cfg.max_steps,
            "error": f"stopped after {cfg.max_steps} steps",
            "events": ctx.events,
        }


KEEP_PICTURES = 2  # a picture fills much of a small AI's working memory: keep the newest


def _forget_old_pictures(messages: list[dict], keep: int) -> None:
    """Replace all but the newest ``keep`` pictures in the conversation by a line of text."""
    with_picture = [
        m
        for m in messages
        if m.get("role") == "user"
        and isinstance(m.get("content"), list)
        and any(p.get("type") == "image_url" for p in m["content"])
    ]
    for m in with_picture[: max(0, len(with_picture) - max(0, keep))]:
        said = " ".join(p.get("text", "") for p in m["content"] if p.get("type") == "text")
        m["content"] = f"{said} (An earlier picture; it is no longer shown to save room.)"


def summarize_events(events: list[dict]) -> str:
    return "\n".join(f"- {e['tool']}({json.dumps(e['args'])[:80]})" for e in events)


# ---------------------------------------------------------------------------
# tools written in the text — for AIs whose own tool format the engine cannot write
# ---------------------------------------------------------------------------

_TROUBLE = ("notimplemented", "not implemented", "template", "jinja", "filter")


def template_trouble(body: str) -> bool:
    low = body.lower()
    return any(t in low for t in _TROUBLE)


WRITTEN_RULES = (
    "\n\nTools. You can use these tools:\n{tools}\n\nTo use one, reply with only this, and "
    'nothing else:\n<tool_call>{{"name": "tool_name", "arguments": {{...}}}}</tool_call>\n'
    "One tool per reply. You will then get its result. When the task is done, reply normally "
    "without <tool_call>."
)


def written_messages(messages: list[dict], schemas: list[dict] | None) -> list[dict]:
    """The conversation with the tools described in the first message and every tool call and
    result as plain text, so the engine never has to write a tool format."""
    lines = []
    for s in schemas:
        f = s.get("function", {})
        params = json.dumps(f.get("parameters", {}).get("properties", {}), ensure_ascii=False)
        lines.append(f"- {f.get('name')}: {f.get('description', '')} Arguments: {params}")
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "system" and schemas:
            out.append(
                {
                    "role": "system",
                    "content": m["content"] + WRITTEN_RULES.format(tools="\n".join(lines)),
                }
            )
        elif role == "assistant" and m.get("tool_calls"):
            text = m.get("content") or ""
            for c in m["tool_calls"]:
                f = c.get("function", {})
                args = f.get("arguments", "{}")
                if not isinstance(args, str):
                    args = json.dumps(args, ensure_ascii=False)
                text += (
                    f'\n<tool_call>{{"name": "{f.get("name")}", "arguments": {args}}}</tool_call>'
                )
            out.append({"role": "assistant", "content": text.strip()})
        elif role == "tool":
            out.append({"role": "user", "content": f"Result of {m.get('name')}:\n{m['content']}"})
        else:
            out.append(m)
    # some templates need user and assistant to take turns: join two in a row
    merged: list[dict] = []
    for m in out:
        if (
            merged
            and m["role"] == merged[-1]["role"]
            and m["role"] in ("user", "assistant")
            and isinstance(m["content"], str)
            and isinstance(merged[-1]["content"], str)
        ):
            merged[-1] = {**merged[-1], "content": merged[-1]["content"] + "\n\n" + m["content"]}
        else:
            merged.append(m)
    return merged


_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
_BARE = re.compile(r"^\s*(?:```(?:json)?\s*)?(\{.*\})\s*(?:```)?\s*$", re.S)


def read_written_calls(content: str) -> tuple[list[dict], str]:
    """Tool calls the AI wrote as text, in the shape the rest of the loop uses."""
    found = _CALL.findall(content)
    if not found:
        m = _BARE.match(content)
        found = [m.group(1)] if m and '"name"' in m.group(1) else []
    calls = []
    for k, raw in enumerate(found):
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(d, dict) or not d.get("name"):
            continue
        args = d.get("arguments", {})
        calls.append(
            {
                "id": f"written-{k}",
                "type": "function",
                "function": {
                    "name": str(d["name"]),
                    "arguments": args if isinstance(args, str) else json.dumps(args),
                },
            }
        )
    if not calls:
        return [], content
    text = _CALL.sub("", content).strip() if _CALL.search(content) else ""
    return calls, text
