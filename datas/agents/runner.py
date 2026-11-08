"""Tool-calling agent loop over any OpenAI-compatible endpoint."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from datas.agents import tools as T
from datas.config import agent_workspace

SYSTEM = (
    "You are an agent running locally on the user's own device through Datas.ar. "
    "You can call tools to list/read/write files in a sandboxed workspace"
    "{shell}{net}. Work step by step: decide, call a tool, read the result, continue. "
    "When the task is complete, answer with a short summary of what you did and where the results are. "
    "Never claim to have done something a tool result does not confirm."
)


@dataclass
class AgentConfig:
    base_url: str = "http://127.0.0.1:8420/v1"
    api_key: str = ""
    model: str = "datas"
    workspace: Path = field(default_factory=agent_workspace)
    allow_shell: bool = False
    allow_network: bool = True
    max_steps: int = 20
    temperature: float = 0.2
    confirm: Callable[[str], bool] | None = None


def run_agent(task: str, cfg: AgentConfig) -> Iterator[dict]:
    """Yield events: {'type': 'assistant'|'tool_call'|'tool_result'|'final'|'error', ...}."""
    ctx = T.ToolContext(
        workspace=cfg.workspace,
        allow_shell=cfg.allow_shell,
        allow_network=cfg.allow_network,
        confirm=cfg.confirm,
    )
    cfg.workspace.mkdir(parents=True, exist_ok=True)
    sys_msg = SYSTEM.format(
        shell=" and run shell commands" if cfg.allow_shell else "",
        net=" and fetch URLs" if cfg.allow_network else "",
    )
    messages: list[dict] = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": task},
    ]
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    with httpx.Client(timeout=httpx.Timeout(600, connect=30)) as client:
        for step in range(cfg.max_steps):
            payload = {
                "model": cfg.model,
                "messages": messages,
                "tools": T.schemas(ctx),
                "tool_choice": "auto",
                "temperature": cfg.temperature,
            }
            try:
                r = client.post(f"{cfg.base_url}/chat/completions", json=payload, headers=headers)
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
        yield {
            "type": "error",
            "step": cfg.max_steps,
            "error": f"stopped after {cfg.max_steps} steps",
            "events": ctx.events,
        }


def summarize_events(events: list[dict]) -> str:
    return "\n".join(f"- {e['tool']}({json.dumps(e['args'])[:80]})" for e in events)
