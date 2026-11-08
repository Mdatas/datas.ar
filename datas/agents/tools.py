"""Built-in agent tools. Each is sandboxed to the agent workspace and permission-gated."""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

MAX_READ = 200_000  # chars
MAX_FETCH = 200_000


@dataclass
class ToolContext:
    workspace: Path
    allow_shell: bool = False
    allow_network: bool = True
    shell_timeout: int = 60
    confirm: Callable[[str], bool] | None = None  # ask before dangerous actions (CLI)
    events: list[dict] = field(default_factory=list)

    def inside(self, rel: str) -> Path:
        p = (self.workspace / rel).resolve()
        if self.workspace.resolve() not in p.parents and p != self.workspace.resolve():
            raise PermissionError(f"path escapes the workspace: {rel}")
        return p


def _schema(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


def list_dir(ctx: ToolContext, path: str = ".") -> str:
    p = ctx.inside(path)
    if not p.exists():
        return f"(not found: {path})"
    rows = []
    for child in sorted(p.iterdir()):
        rows.append(
            f"{'d' if child.is_dir() else 'f'} {child.stat().st_size:>10} {child.relative_to(ctx.workspace)}"
        )
    return "\n".join(rows) or "(empty)"


def read_file(ctx: ToolContext, path: str) -> str:
    p = ctx.inside(path)
    data = p.read_text(errors="replace")
    return data[:MAX_READ] + ("\n…(truncated)" if len(data) > MAX_READ else "")


def write_file(ctx: ToolContext, path: str, content: str) -> str:
    p = ctx.inside(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} chars to {p.relative_to(ctx.workspace)}"


def run_command(ctx: ToolContext, command: str) -> str:
    if not ctx.allow_shell:
        return "DENIED: shell access is off. Start the agent with --allow-shell to enable it."
    if ctx.confirm and not ctx.confirm(f"Run shell command?\n  {command}"):
        return "DENIED by user."
    try:
        out = subprocess.run(
            shlex.split(command),
            cwd=ctx.workspace,
            capture_output=True,
            text=True,
            timeout=ctx.shell_timeout,
        )
    except subprocess.TimeoutExpired:
        return f"timeout after {ctx.shell_timeout}s"
    except (OSError, ValueError) as e:
        return f"error: {e}"
    text = (out.stdout + ("\n[stderr]\n" + out.stderr if out.stderr else "")).strip()
    return f"exit {out.returncode}\n{text[:MAX_READ]}"


def fetch_url(ctx: ToolContext, url: str) -> str:
    if not ctx.allow_network:
        return "DENIED: network access is off (--no-network)."
    if not url.startswith(("http://", "https://")):
        return "only http(s) URLs"
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "datas-agent"})
    except httpx.HTTPError as e:
        return f"error: {e}"
    ctype = r.headers.get("content-type", "")
    body = (
        r.text
        if ("text" in ctype or "json" in ctype or "xml" in ctype)
        else f"({len(r.content)} bytes of {ctype})"
    )
    return f"HTTP {r.status_code} {ctype}\n{body[:MAX_FETCH]}"


TOOLS: dict[str, tuple[Callable[..., str], dict]] = {
    "list_dir": (
        list_dir,
        _schema(
            "list_dir", "List files in the workspace directory.", {"path": {"type": "string"}}, []
        ),
    ),
    "read_file": (
        read_file,
        _schema(
            "read_file",
            "Read a text file from the workspace.",
            {"path": {"type": "string"}},
            ["path"],
        ),
    ),
    "write_file": (
        write_file,
        _schema(
            "write_file",
            "Write a text file inside the workspace (creates folders).",
            {"path": {"type": "string"}, "content": {"type": "string"}},
            ["path", "content"],
        ),
    ),
    "run_command": (
        run_command,
        _schema(
            "run_command",
            "Run a shell command inside the workspace (if allowed).",
            {"command": {"type": "string"}},
            ["command"],
        ),
    ),
    "fetch_url": (
        fetch_url,
        _schema(
            "fetch_url",
            "Fetch a web page or API (GET) and return its text.",
            {"url": {"type": "string"}},
            ["url"],
        ),
    ),
}


def schemas(ctx: ToolContext) -> list[dict]:
    out = []
    for name, (_, schema) in TOOLS.items():
        if name == "run_command" and not ctx.allow_shell:
            continue
        if name == "fetch_url" and not ctx.allow_network:
            continue
        out.append(schema)
    return out


def call(ctx: ToolContext, name: str, arguments: str | dict) -> str:
    fn = TOOLS.get(name)
    if not fn:
        return f"unknown tool {name}"
    try:
        args: dict[str, Any] = (
            json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        )
    except json.JSONDecodeError as e:
        return f"bad arguments: {e}"
    try:
        result = fn[0](ctx, **args)
    except TypeError as e:
        result = f"bad arguments: {e}"
    except PermissionError as e:
        result = f"DENIED: {e}"
    except Exception as e:  # noqa: BLE001
        result = f"error: {type(e).__name__}: {e}"
    ctx.events.append({"tool": name, "args": args, "result": result[:2000]})
    return result
