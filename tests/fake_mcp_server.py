"""A tiny program that speaks the Model Context Protocol over stdin/stdout, for the tests.

    python fake_mcp_server.py --root <folder>

Tools: ``add`` (numbers), ``note_save`` (writes a text file inside --root), ``fail``. The tool
list is served in two pages, and the server pings the client once, as real servers may.
"""

import json
import sys
from pathlib import Path

root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else Path(".")
TOOLS = [
    {
        "name": "add",
        "description": "Add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "note.save",
        "description": "Save a note as a text file",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "text": {"type": "string"}},
            "required": ["name", "text"],
        },
    },
    {"name": "fail", "description": "Always fails", "inputSchema": {"type": "object"}},
]


def out(obj) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


print("starting (this line goes to stderr, as logs should)", file=sys.stderr)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        out(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": params.get("protocolVersion"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake", "version": "1.0"},
                },
            }
        )
    elif method == "notifications/initialized":
        out({"jsonrpc": "2.0", "id": "srv-1", "method": "ping"})  # the client must answer this
    elif method == "tools/list":
        if not params.get("cursor"):
            out({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS[:2], "nextCursor": "p2"}})
        else:
            out({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS[2:]}})
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name == "add":
            text, err = str(args["a"] + args["b"]), False
        elif name == "note.save":
            p = root / Path(args["name"]).name
            p.write_text(args["text"], encoding="utf-8")
            text, err = f"saved {p.name}", False
        else:
            text, err = "this tool always fails", True
        out(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"content": [{"type": "text", "text": text}], "isError": err},
            }
        )
    elif mid is not None and method:
        out({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown method"}})
