"""A small client for the Model Context Protocol (MCP), the open standard many programs now
speak so that an AI can use them as tools.

Only what Datas needs, with no extra dependency: the "stdio" transport (the program is started
by Datas and talks through its standard input and output — no network port), the handshake,
listing the tools and calling one. Programs that work this way include the ArtCraft "Craft"
apps (for instance ``pdfcraft-cli mcp --root <folder>``) and hundreds of community servers.

A server is described the way every MCP client describes it::

    {"mcpServers": {"pdfcraft": {"command": "pdfcraft-cli", "args": ["mcp", "--root", "{root}"]}}}

``{root}`` is replaced by the folder the agent may work in. The user's own entries live in
``<data>/mcp.json``; Datas adds the Craft apps it finds installed (see ``datas.programs``).

Nothing is started until an agent run actually needs it, each server lives only for that run,
and every tool call goes through the same "may I?" approval as the agent's other actions.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from datas import __version__
from datas.config import home

PROTOCOL = "2025-06-18"
MAX_TOOLS_PER_SERVER = 24  # keep the list a small AI has to read short
MAX_RESULT = 60_000


class McpError(RuntimeError):
    pass


class McpServer:
    """One running MCP program (stdio). Thread-safe for one caller at a time."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict | None = None,
        cwd: str | None = None,
    ):
        self.name, self.command, self.args = name, command, list(args)
        self.env, self.cwd = env or {}, cwd
        self.proc: subprocess.Popen | None = None
        self.info: dict = {}
        self.tools: list[dict] = []
        self._id = 0
        self._q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._stderr: list[str] = []

    # ---- lifecycle ----------------------------------------------------------
    def start(self, timeout: float = 30) -> None:
        env = os.environ.copy()
        env.update({k: str(v) for k, v in self.env.items()})
        creation = {}
        if sys.platform == "win32":
            creation["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=self.cwd,
                **creation,
            )
        except OSError as e:
            raise McpError(f"{self.name}: could not start {self.command} ({e})") from e
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        self.info = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "Datas.ar", "version": __version__},
            },
            timeout,
        )
        self.notify("notifications/initialized")
        self.tools = self._list_tools(timeout)

    def stop(self) -> None:
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.close()  # the polite way: the server sees end of input and exits
                p.wait(3)
            except Exception:  # noqa: BLE001
                p.terminate()
                try:
                    p.wait(3)
                except Exception:  # noqa: BLE001
                    p.kill()

    def alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    # ---- wire ---------------------------------------------------------------
    def _read_out(self) -> None:
        p = self.proc
        try:
            for raw in p.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue  # a server that prints something else on stdout: ignore the line
                if isinstance(msg, dict) and "method" in msg and "id" in msg:
                    self._answer_server(msg)
                elif isinstance(msg, dict) and "id" in msg:
                    self._q.put(msg)
        except (OSError, ValueError):
            pass
        self._q.put({"closed": True})

    def _read_err(self) -> None:
        try:
            for raw in self.proc.stderr:
                self._stderr.append(raw.decode("utf-8", errors="replace").rstrip())
                del self._stderr[:-40]
        except (OSError, ValueError, AttributeError):
            pass

    def _send(self, obj: dict) -> None:
        if not self.alive():
            raise McpError(f"{self.name} is not running")
        try:
            self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
            self.proc.stdin.flush()
        except (OSError, ValueError) as e:
            raise McpError(f"{self.name} stopped ({e})") from e

    def _answer_server(self, msg: dict) -> None:
        """The server asked us something. We offer no extra abilities: answer pings, decline
        the rest."""
        try:
            if msg.get("method") == "ping":
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
            else:
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "error": {"code": -32601, "message": "not supported by this client"},
                    }
                )
        except McpError:
            pass

    def notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def request(self, method: str, params: dict | None = None, timeout: float = 120) -> dict:
        with self._lock:
            self._id += 1
            rid = self._id
            msg = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params is not None:
                msg["params"] = params
            self._send(msg)
            deadline = time.time() + timeout
            while True:
                try:
                    r = self._q.get(timeout=max(0.1, deadline - time.time()))
                except queue.Empty:
                    raise McpError(f"{self.name} did not answer in {timeout:.0f} s") from None
                if r.get("closed"):
                    tail = " ".join(self._stderr[-3:])[:300]
                    raise McpError(f"{self.name} stopped unexpectedly. {tail}".strip())
                if r.get("id") != rid:
                    continue  # an answer to something we stopped waiting for
                if "error" in r:
                    e = r["error"] or {}
                    raise McpError(f"{self.name}: {e.get('message', 'error')}")
                return r.get("result") or {}

    # ---- tools --------------------------------------------------------------
    def _list_tools(self, timeout: float) -> list[dict]:
        out: list[dict] = []
        cursor = None
        for _ in range(20):
            r = self.request("tools/list", {"cursor": cursor} if cursor else {}, timeout)
            out += [t for t in r.get("tools", []) if isinstance(t, dict) and t.get("name")]
            cursor = r.get("nextCursor")
            if not cursor:
                break
        return out

    def call(self, tool: str, arguments: dict, timeout: float = 300) -> str:
        r = self.request("tools/call", {"name": tool, "arguments": arguments or {}}, timeout)
        parts = []
        for c in r.get("content", []) or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text":
                parts.append(str(c.get("text", "")))
            elif c.get("type") == "resource" and isinstance(c.get("resource"), dict):
                parts.append(str(c["resource"].get("text") or c["resource"].get("uri") or ""))
            else:
                parts.append(f"({c.get('type', 'content')} not shown)")
        if not parts and r.get("structuredContent") is not None:
            parts.append(json.dumps(r["structuredContent"], ensure_ascii=False))
        text = "\n".join(p for p in parts if p).strip() or "(done)"
        if len(text) > MAX_RESULT:
            text = text[:MAX_RESULT] + "\n…(truncated)"
        return ("ERROR: " + text) if r.get("isError") else text


# ---------------------------------------------------------------------------
# which servers exist
# ---------------------------------------------------------------------------


def config_path() -> Path:
    return home() / "mcp.json"


def user_servers() -> dict[str, dict]:
    """The user's own entries (``<data>/mcp.json``), in the usual ``mcpServers`` shape."""
    try:
        d = json.loads(config_path().read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    servers = d.get("mcpServers") if isinstance(d, dict) else None
    out = {}
    for name, s in (servers or {}).items():
        if isinstance(s, dict) and s.get("command") and not s.get("disabled"):
            out[str(name)] = {
                "command": str(s["command"]),
                "args": [str(a) for a in s.get("args", [])],
                "env": s.get("env") or {},
                "source": "yours",
            }
    return out


def save_user_server(name: str, command: str, args: list[str], env: dict | None = None) -> dict:
    name = "".join(c for c in name if c.isalnum() or c in "-_")[:40]
    if not name or not command.strip():
        raise ValueError("a connection needs a short name and a command")
    try:
        d = json.loads(config_path().read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except (ValueError, OSError):
        d = {}
    d.setdefault("mcpServers", {})[name] = {
        "command": command.strip(),
        "args": [str(a) for a in args],
        **({"env": env} if env else {}),
    }
    tmp = config_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    tmp.replace(config_path())
    return {"name": name, **d["mcpServers"][name]}


def remove_user_server(name: str) -> bool:
    try:
        d = json.loads(config_path().read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if name not in (d.get("mcpServers") or {}):
        return False
    d["mcpServers"].pop(name)
    config_path().write_text(json.dumps(d, indent=1), encoding="utf-8")
    return True


def all_servers() -> dict[str, dict]:
    """The user's entries plus the Craft apps found on this computer (the user's win by name)."""
    from datas import programs

    out = dict(programs.craft_mcp_servers())
    out.update(user_servers())
    return out


def fill(args: list[str], root: Path) -> list[str]:
    return [a.replace("{root}", str(root)) for a in args]


def safe_name(server: str, tool: str) -> str:
    """Tool name as the AI sees it: letters, digits, _ and - only (what chat APIs accept)."""
    raw = f"{server}__{tool}"
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in raw)[:64]


class Session:
    """The MCP servers of one agent run: started on first use, stopped at the end."""

    def __init__(self, root: Path, only: list[str] | None = None):
        self.root = root
        self.specs = {k: v for k, v in all_servers().items() if only is None or k in only}
        self.servers: dict[str, McpServer] = {}
        self.errors: dict[str, str] = {}
        self.index: dict[str, tuple[str, str]] = {}  # tool name the AI sees → (server, tool)

    def start_all(self) -> None:
        for name, spec in self.specs.items():
            if name in self.servers or name in self.errors:
                continue
            srv = McpServer(name, spec["command"], fill(spec["args"], self.root), spec.get("env"))
            try:
                srv.start()
            except McpError as e:
                self.errors[name] = str(e)
                srv.stop()
                continue
            self.servers[name] = srv
            for t in srv.tools[:MAX_TOOLS_PER_SERVER]:
                self.index[safe_name(name, t["name"])] = (name, t["name"])

    def schemas(self) -> list[dict]:
        out = []
        for shown, (server, tool) in self.index.items():
            t = next(x for x in self.servers[server].tools if x["name"] == tool)
            schema = t.get("inputSchema")
            if not isinstance(schema, dict) or schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": shown,
                        "description": f"[{server}] " + str(t.get("description") or tool)[:500],
                        "parameters": schema,
                    },
                }
            )
        return out

    def has(self, shown: str) -> bool:
        return shown in self.index

    def call(self, shown: str, arguments: dict) -> str:
        server, tool = self.index[shown]
        try:
            return self.servers[server].call(tool, arguments)
        except McpError as e:
            return f"ERROR: {e}"

    def stop(self) -> None:
        for s in self.servers.values():
            s.stop()
        self.servers.clear()
        self.index.clear()
