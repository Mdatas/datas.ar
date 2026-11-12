"""Built-in agent tools. Every file operation is confined to the agent's own workspace plus the
folders the user granted for this session (``ToolContext.roots``); deletions go to a trash folder
inside the workspace, never straight to the void; commands run only when explicitly allowed."""

from __future__ import annotations

import fnmatch
import html
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse, urlsplit

import httpx

from datas import netguard
from datas.agents import pc_tools, things_tools

MAX_READ = 200_000  # chars
MAX_FETCH = 200_000
MAX_LIST = 400


RISKY = {
    "run_command",
    "run_program",
    "delete_file",
    "move_file",
    "copy_file",
    "write_file",
    "save_document",
    "convert_file",
    "open_path",
}


@dataclass
class ToolContext:
    workspace: Path
    roots: list[Path] = field(default_factory=list)  # extra folders the user granted
    allow_shell: bool = False
    allow_network: bool = True
    allow_local: bool = False  # web tools may open addresses inside the user's own network
    shell_timeout: int = 60
    # ask = "all" (approve every action) | "risky" (only what touches your folders, runs commands,
    # opens things) | "none" (just do it, I'm watching). confirm(text) -> True/False blocks until answered.
    ask: str = "risky"
    confirm: Callable[[str], bool] | None = None
    should_stop: Callable[[], bool] | None = None
    events: list[dict] = field(default_factory=list)
    lang: str = "en"
    mcp: Any = None  # datas.mcp.Session: tools offered by programs that speak MCP (ArtCraft…)
    # hardware and devices on the network (datas/agents/things_tools.py), each its own switch
    allow_things: bool = False
    allow_control: bool = False  # the mouse and keyboard, experimental
    vision: bool = False  # the AI that is running understands pictures
    images: list[dict] = field(default_factory=list)  # pictures waiting to be shown to the AI
    screen_picture: tuple[int, int] | None = None  # size of the last picture of the screen
    # "configure my PC" (datas/agents/pc_tools.py): apps, settings pages, a few settings
    allow_setup: bool = False
    sign_in_wait: Callable[[str], bool] | None = None  # waits while the person signs in

    def is_risky(self, name: str, args: dict) -> bool:
        """Risky = commands, programs, opening things, tools inside other programs, and
        writes/moves/deletes that touch a granted folder (inside the agent's own workspace
        everything is reversible via _trash)."""
        if name in ("run_command", "run_program", "open_path") or name in things_tools.ACTS:
            return True
        if name in pc_tools.ACTS:
            return True
        if self.mcp is not None and self.mcp.has(name):
            return True
        if name not in RISKY:
            return False
        ws = self.workspace.resolve()
        for key in ("path", "source", "destination"):
            v = args.get(key)
            if not v:
                continue
            try:
                p = self.inside(v)
            except PermissionError:
                return True
            if p != ws and ws not in p.parents:
                return True
        return False

    def all_roots(self) -> list[Path]:
        return [self.workspace.resolve()] + [r.resolve() for r in self.roots]

    def inside(self, rel: str) -> Path:
        """Resolve ``rel`` (workspace-relative, or absolute inside a granted folder) safely."""
        raw = Path(os.path.expanduser(rel or "."))
        p = (raw if raw.is_absolute() else self.workspace / raw).resolve()
        for root in self.all_roots():
            if p == root or root in p.parents:
                return p
        raise PermissionError(
            f"{rel} is outside the folders the agent may use: "
            + ", ".join(str(r) for r in self.all_roots())
        )

    def trash(self) -> Path:
        t = self.workspace / "_trash"
        t.mkdir(parents=True, exist_ok=True)
        return t


def _schema(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


def _show(ctx: ToolContext, p: Path) -> str:
    try:
        return str(p.relative_to(ctx.workspace.resolve()))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# files


def list_dir(ctx: ToolContext, path: str = ".") -> str:
    p = ctx.inside(path)
    if not p.exists():
        return f"(not found: {path})"
    if p.is_file():
        return f"f {p.stat().st_size:>10} {_show(ctx, p)}"
    rows = []
    for child in sorted(p.iterdir(), key=lambda c: (c.is_file(), c.name.lower()))[:MAX_LIST]:
        try:
            size = child.stat().st_size if child.is_file() else 0
            mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(child.stat().st_mtime))
        except OSError:
            size, mtime = 0, "?"
        rows.append(f"{'d' if child.is_dir() else 'f'} {size:>10} {mtime} {child.name}")
    return f"{_show(ctx, p)}:\n" + ("\n".join(rows) or "(empty)")


def find_files(ctx: ToolContext, pattern: str, path: str = ".", max_results: int = 200) -> str:
    """Glob-style search (``*.pdf``, ``report*``) under a folder, recursively."""
    p = ctx.inside(path)
    out = []
    for child in p.rglob("*"):
        if len(out) >= max_results:
            out.append("…(more)")
            break
        if fnmatch.fnmatch(child.name.lower(), pattern.lower()):
            out.append(f"{'d' if child.is_dir() else 'f'} {_show(ctx, child)}")
    return "\n".join(out) or "(nothing matched)"


def read_file(ctx: ToolContext, path: str) -> str:
    """Text of a file; PDF, Word, Excel, PowerPoint and web pages are converted to text."""
    from datas import docs

    p = ctx.inside(path)
    if p.is_dir():
        return list_dir(ctx, path)
    if not p.exists():
        return f"(not found: {path})"
    if p.suffix.lower() in docs.RICH_SUFFIXES:
        try:
            text = docs.extract_text(p.name, p.read_bytes())
        except ValueError as e:
            return f"(could not read {p.name}: {e})"
    else:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"(could not read {p.name}: {e})"
    return text[:MAX_READ] + ("\n…(truncated)" if len(text) > MAX_READ else "")


def save_document(ctx: ToolContext, path: str, content: str) -> str:
    """Write Markdown ``content`` as a real document; the file extension chooses the format:
    .docx (Word), .xlsx (Excel: each Markdown table becomes a sheet, cells starting with = are
    formulas), .pptx (PowerPoint: each ## heading is a slide), .pdf, .html, .md, .txt."""
    from datas import export

    p = ctx.inside(path)
    fmt = p.suffix.lower().lstrip(".")
    if fmt not in export.FORMATS:
        return f"refused: use one of these endings: {', '.join('.' + f for f in export.FORMATS)}"
    if p.exists():
        return f"refused: {_show(ctx, p)} already exists (choose another name)"
    try:
        export.render(content, fmt, p, lang=ctx.lang)
    except Exception as e:  # noqa: BLE001
        return f"could not write {p.name}: {e}"
    return f"saved {_show(ctx, p)} ({p.stat().st_size} bytes)"


def convert_file(ctx: ToolContext, source: str, to: str) -> str:
    """Convert a file to another format with whatever installed program can do it."""
    from datas import programs

    src = ctx.inside(source)
    try:
        out = programs.convert(src, to, fetch_ffmpeg=ctx.allow_network)
    except RuntimeError as e:
        return f"could not convert: {e}"
    return f"converted {_show(ctx, src)} → {_show(ctx, out)}"


def list_programs(ctx: ToolContext) -> str:
    """Programs on this computer the agent can use, and what each is for."""
    from datas import programs

    rows = [
        f"- {p['id']}: {p['name']} — {p['does']['en']}"
        + (" (has its own tools for you)" if p.get("agent_tools") else "")
        for p in programs.detect()
        if p["found"]
    ]
    conv = "convert_file works for: Markdown/text → docx, xlsx, pptx, pdf, html (always); other conversions depend on the programs above."
    return ("\n".join(rows) or "(no extra programs found on this computer)") + "\n" + conv


def run_program(ctx: ToolContext, program: str, arguments: list[str] | str = "") -> str:
    """Run one of the programs from list_programs with arguments (no shell). Runs in the
    workspace; relative file names refer to it."""
    from datas import programs

    exe = programs.ffmpeg(ctx.allow_network) if program == "ffmpeg" else programs.find(program)
    if not exe:
        return f"(program {program!r} was not found; see list_programs)"
    if isinstance(arguments, str):
        try:
            arguments = shlex.split(arguments, posix=platform.system() != "Windows")
        except ValueError as e:
            return f"bad arguments: {e}"
    args = [str(a) for a in arguments]
    if not ctx.allow_shell:
        # Without "may run commands", a found program is for opening, converting and exporting
        # inside the agent's folders — not a side door (see datas/programs.py).
        bad = programs.runs_code(program, args)
        if bad:
            return (
                f"DENIED: {bad!r} is a script, or an option that can make {program} run code "
                "or start another program. That needs 'May run commands' switched on in the "
                "agent window. (To read, write or convert a file use read_file, save_document "
                "or convert_file.)"
            )
        for url in programs.network_addresses(args):
            if not ctx.allow_network:
                return f"DENIED: {url!r} is a network address and internet is off for this session."
            try:  # the same question as for web pages: is this inside the user's own network?
                netguard.check_url("http://" + urlsplit(url).netloc, ctx.allow_local)
            except (netguard.Blocked, ValueError) as e:
                return f"DENIED: {url!r}: {e}"
        outside = programs.outside_paths(program, args, ctx.all_roots(), ctx.workspace)
        if outside:
            return (
                f"DENIED: {outside[0]!r} is outside the folders the agent may use: "
                + ", ".join(str(r) for r in ctx.all_roots())
                + ". The user can add that folder in the agent window."
            )
    try:
        out = subprocess.run(
            [exe, *args],
            cwd=ctx.workspace,
            capture_output=True,
            text=True,
            timeout=max(ctx.shell_timeout, 900),
        )
    except subprocess.TimeoutExpired:
        return "stopped: the program ran for more than 15 minutes"
    except OSError as e:
        return f"error: {e}"
    text = (out.stdout + ("\n[stderr]\n" + out.stderr if out.stderr else "")).strip()
    return f"exit {out.returncode}\n{text[-MAX_READ:]}"


def write_file(ctx: ToolContext, path: str, content: str) -> str:
    p = ctx.inside(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {_show(ctx, p)}"


def make_dir(ctx: ToolContext, path: str) -> str:
    p = ctx.inside(path)
    p.mkdir(parents=True, exist_ok=True)
    return f"folder ready: {_show(ctx, p)}"


def move_file(ctx: ToolContext, source: str, destination: str) -> str:
    """Move or rename. If ``destination`` is an existing folder, the file goes inside it."""
    src = ctx.inside(source)
    dst = ctx.inside(destination)
    if not src.exists():
        return f"(not found: {source})"
    if dst.is_dir() or destination.endswith(("/", "\\")):  # a folder: put the file inside it
        dst.mkdir(parents=True, exist_ok=True)
        dst = dst / src.name
    if dst.exists():
        return f"refused: {_show(ctx, dst)} already exists"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"moved {_show(ctx, src)} → {_show(ctx, dst)}"


def copy_file(ctx: ToolContext, source: str, destination: str) -> str:
    src = ctx.inside(source)
    dst = ctx.inside(destination)
    if not src.exists():
        return f"(not found: {source})"
    if dst.is_dir() or destination.endswith(("/", "\\")):
        dst.mkdir(parents=True, exist_ok=True)
        dst = dst / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return f"copied {_show(ctx, src)} → {_show(ctx, dst)}"


def delete_file(ctx: ToolContext, path: str) -> str:
    """Never destroys: moves the file or folder into the workspace's _trash folder."""
    p = ctx.inside(path)
    if not p.exists():
        return f"(not found: {path})"
    if p.resolve() in ctx.all_roots():
        return "refused: that is one of the granted folders itself"
    target = ctx.trash() / f"{int(time.time())}-{p.name}"
    shutil.move(str(p), str(target))
    return (
        f"moved to trash: {_show(ctx, p)} → {_show(ctx, target)} (restore it from there if needed)"
    )


# ---------------------------------------------------------------------------
# computer


def open_path(ctx: ToolContext, target: str, program: str = "") -> str:
    """Open a file, folder or web page with whatever the user normally uses for it — or, with
    ``program`` (an id from list_programs), in that program."""
    if target.startswith(("http://", "https://")):
        if not ctx.allow_network:
            return "DENIED: internet is off for this session."
        what = target
    else:
        what = str(ctx.inside(target))
        if not Path(what).exists():
            return f"(not found: {target})"
    if program:
        from datas import programs

        try:
            programs.open_program(program, what)
        except (RuntimeError, OSError) as e:
            return f"could not open with {program}: {e}"
        return f"opened {what} in {program}"
    try:
        if platform.system() == "Windows":
            os.startfile(what)  # type: ignore[attr-defined]  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", what])
        else:
            subprocess.Popen(
                ["xdg-open", what], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception as e:  # noqa: BLE001
        return f"could not open: {e}"
    return f"opened {what}"


def run_command(ctx: ToolContext, command: str) -> str:
    if not ctx.allow_shell:
        return "DENIED: running commands is off. The user can allow it with the switch in the agent window."
    try:
        out = subprocess.run(
            shlex.split(command, posix=platform.system() != "Windows"),
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


# ---------------------------------------------------------------------------
# internet


def web_search(ctx: ToolContext, query: str, max_results: int = 8) -> str:
    """DuckDuckGo's HTML endpoint: no API key, no tracking parameters."""
    if not ctx.allow_network:
        return "DENIED: internet is off for this session."
    try:
        r = netguard.get(
            "https://html.duckduckgo.com/html/", ctx.allow_local, params={"q": query}, timeout=20
        )
    except netguard.Blocked as e:
        return f"search blocked: {e}"
    except httpx.HTTPError as e:
        return f"search failed: {e}"
    if r.status >= 400:
        return f"search failed: HTTP {r.status}"
    items = []
    for m in re.finditer(
        r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'(?:<a class="result__snippet"[^>]*>(.*?)</a>)?',
        r.text,
        re.S,
    ):
        href, title, snip = m.group(1), m.group(2), m.group(3) or ""
        if "uddg=" in href:
            href = unquote(href.split("uddg=")[1].split("&")[0])
        clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()  # noqa: E731
        items.append(f"- {clean(title)}\n  {href}\n  {clean(snip)}")
        if len(items) >= max_results:
            break
    return "\n".join(items) or f"(no results for {query!r}; try other words)"


def fetch_url(ctx: ToolContext, url: str) -> str:
    """Public web pages only (see datas.netguard); PDFs come back as their text."""
    if not ctx.allow_network:
        return "DENIED: internet is off for this session."
    try:
        r = netguard.get(url, ctx.allow_local)
    except netguard.Blocked as e:
        return f"DENIED: {e}"
    except httpx.HTTPError as e:
        return f"error: {e}"
    ctype = r.content_type
    if "html" in ctype:
        text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        body = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()
    elif "text" in ctype or "json" in ctype or "xml" in ctype:
        body = r.text
    elif "pdf" in ctype or r.url.lower().endswith(".pdf"):
        try:
            from datas import docs

            body = docs.extract_text("page.pdf", r.body)
        except ValueError as e:
            body = f"(a PDF that could not be read: {e})"
    else:
        body = f"({len(r.body)} bytes of {ctype})"
    return f"HTTP {r.status} {ctype} {urlparse(r.url).netloc}\n{body[:MAX_FETCH]}"


def search_url(query: str) -> str:
    return "https://duckduckgo.com/?q=" + quote_plus(query)


# ---------------------------------------------------------------------------

S = {"type": "string"}
TOOLS: dict[str, tuple[Callable[..., str], dict]] = {
    "list_dir": (
        list_dir,
        _schema(
            "list_dir",
            "List a folder (workspace-relative or a granted absolute path).",
            {"path": S},
            [],
        ),
    ),
    "find_files": (
        find_files,
        _schema(
            "find_files",
            "Find files by name pattern (e.g. *.pdf) under a folder, recursively.",
            {"pattern": S, "path": S},
            ["pattern"],
        ),
    ),
    "read_file": (
        read_file,
        _schema(
            "read_file",
            "Read a file as text; PDF, Word, Excel, PowerPoint and web pages are converted.",
            {"path": S},
            ["path"],
        ),
    ),
    "save_document": (
        save_document,
        _schema(
            "save_document",
            "Create a document from Markdown; the ending of the path picks the format: .docx, "
            ".xlsx (tables become sheets, cells starting with = are formulas), .pptx (each ## "
            "heading is a slide), .pdf, .html, .md, .txt.",
            {"path": S, "content": S},
            ["path", "content"],
        ),
    ),
    "convert_file": (
        convert_file,
        _schema(
            "convert_file",
            "Convert a file to another format (e.g. docx→pdf, svg→png, scad→stl, mp4→mp3) using "
            "the programs installed on this computer. 'to' is the new ending, e.g. pdf.",
            {"source": S, "to": S},
            ["source", "to"],
        ),
    ),
    "list_programs": (
        list_programs,
        _schema(
            "list_programs",
            "List the programs on this computer you can use (LibreOffice, Inkscape, Blender, "
            "FFmpeg, ArtCraft apps…) and what each is for.",
            {},
            [],
        ),
    ),
    "run_program": (
        run_program,
        _schema(
            "run_program",
            "Run one of the programs from list_programs with arguments, e.g. program=ffmpeg, "
            "arguments=['-i','in.mp4','-ss','10','-t','5','clip.mp4'].",
            {"program": S, "arguments": {"type": "array", "items": S}},
            ["program"],
        ),
    ),
    "write_file": (
        write_file,
        _schema(
            "write_file",
            "Write a text file (creates folders). Overwrites.",
            {"path": S, "content": S},
            ["path", "content"],
        ),
    ),
    "make_dir": (make_dir, _schema("make_dir", "Create a folder.", {"path": S}, ["path"])),
    "move_file": (
        move_file,
        _schema(
            "move_file",
            "Move or rename a file/folder. Destination may be a folder.",
            {"source": S, "destination": S},
            ["source", "destination"],
        ),
    ),
    "copy_file": (
        copy_file,
        _schema(
            "copy_file",
            "Copy a file/folder.",
            {"source": S, "destination": S},
            ["source", "destination"],
        ),
    ),
    "delete_file": (
        delete_file,
        _schema(
            "delete_file",
            "Move a file/folder to the agent's trash (reversible).",
            {"path": S},
            ["path"],
        ),
    ),
    "open_path": (
        open_path,
        _schema(
            "open_path",
            "Open a file, folder or web page for the user with their usual app, or in a "
            "program from list_programs (program=its id).",
            {"target": S, "program": S},
            ["target"],
        ),
    ),
    "run_command": (
        run_command,
        _schema(
            "run_command",
            "Run a shell command inside the workspace (only when the user allowed it).",
            {"command": S},
            ["command"],
        ),
    ),
    "web_search": (
        web_search,
        _schema(
            "web_search",
            "Search the web; returns titles, links and snippets.",
            {"query": S},
            ["query"],
        ),
    ),
    "fetch_url": (
        fetch_url,
        _schema(
            "fetch_url", "Open a web page or API (GET) and return its text.", {"url": S}, ["url"]
        ),
    ),
}


def schemas(ctx: ToolContext) -> list[dict]:
    out = []
    for name, (_, schema) in TOOLS.items():
        if name == "run_command" and not ctx.allow_shell:
            continue
        if name in ("fetch_url", "web_search") and not ctx.allow_network:
            continue
        out.append(schema)
    out += things_tools.schemas(ctx)
    out += pc_tools.schemas(ctx)
    if ctx.mcp is not None:
        out += ctx.mcp.schemas()
    return out


def call(ctx: ToolContext, name: str, arguments: str | dict) -> str:
    fn = TOOLS.get(name)
    is_thing = name in things_tools.TOOLS
    is_pc = name in pc_tools.TOOLS and ctx.allow_setup
    is_mcp = ctx.mcp is not None and ctx.mcp.has(name)
    if not fn and not is_mcp and not is_thing and not is_pc:
        return f"unknown tool {name}"
    try:
        args: dict[str, Any] = (
            json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        )
    except json.JSONDecodeError as e:
        return f"bad arguments: {e}"
    if ctx.should_stop and ctx.should_stop():
        result = "STOPPED by user."
        ctx.events.append({"tool": name, "args": args, "result": result})
        return result
    if ctx.confirm and (ctx.ask == "all" or (ctx.ask == "risky" and ctx.is_risky(name, args))):
        pretty = ", ".join(f"{k}={str(v)[:120]}" for k, v in args.items())
        plain = (
            things_tools.confirm_text(name, args, ctx.lang)
            if is_thing
            else pc_tools.confirm_text(name, args, ctx.lang)
            if is_pc
            else None
        )
        if not ctx.confirm(plain or f"{name}({pretty})"):
            result = "DENIED by user."
            ctx.events.append({"tool": name, "args": args, "result": result})
            return result
    try:
        if is_thing:
            result = things_tools.run(ctx, name, args)
        elif is_pc:
            result = pc_tools.TOOLS[name][0](ctx, **args)
        else:
            result = ctx.mcp.call(name, args) if is_mcp else fn[0](ctx, **args)
    except TypeError as e:
        result = f"bad arguments: {e}"
    except PermissionError as e:
        result = f"DENIED: {e}"
    except Exception as e:  # noqa: BLE001
        result = f"error: {type(e).__name__}: {e}"
    ctx.events.append({"tool": name, "args": args, "result": result[:2000]})
    return result
