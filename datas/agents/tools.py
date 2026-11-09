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
from urllib.parse import quote_plus, unquote, urlparse

import httpx

MAX_READ = 200_000  # chars
MAX_FETCH = 200_000
MAX_LIST = 400


@dataclass
class ToolContext:
    workspace: Path
    roots: list[Path] = field(default_factory=list)  # extra folders the user granted
    allow_shell: bool = False
    allow_network: bool = True
    shell_timeout: int = 60
    confirm: Callable[[str], bool] | None = None  # ask before dangerous actions (CLI)
    events: list[dict] = field(default_factory=list)

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
    p = ctx.inside(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages[:60])
        except Exception as e:  # noqa: BLE001
            return f"(could not read PDF: {e})"
    elif suffix == ".docx":
        try:
            import zipfile

            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            text = re.sub(r"</w:p>", "\n", xml)
            text = html.unescape(re.sub(r"<[^>]+>", "", text))
        except Exception as e:  # noqa: BLE001
            return f"(could not read .docx: {e})"
    else:
        try:
            text = p.read_text(errors="replace")
        except IsADirectoryError:
            return list_dir(ctx, path)
    return text[:MAX_READ] + ("\n…(truncated)" if len(text) > MAX_READ else "")


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


def open_path(ctx: ToolContext, target: str) -> str:
    """Open a file, folder or web page with whatever the user normally uses for it."""
    if target.startswith(("http://", "https://")):
        if not ctx.allow_network:
            return "DENIED: internet is off for this session."
        what = target
    else:
        what = str(ctx.inside(target))
        if not Path(what).exists():
            return f"(not found: {target})"
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
    if ctx.confirm and not ctx.confirm(f"Run shell command?\n  {command}"):
        return "DENIED by user."
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
        r = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 datas.ar"},
            timeout=20,
            follow_redirects=True,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        return f"search failed: {e}"
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
    if not ctx.allow_network:
        return "DENIED: internet is off for this session."
    if not url.startswith(("http://", "https://")):
        return "only http(s) URLs"
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "datas-agent"})
    except httpx.HTTPError as e:
        return f"error: {e}"
    ctype = r.headers.get("content-type", "")
    if "html" in ctype:
        text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        body = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()
    elif "text" in ctype or "json" in ctype or "xml" in ctype:
        body = r.text
    else:
        body = f"({len(r.content)} bytes of {ctype})"
    return f"HTTP {r.status_code} {ctype} {urlparse(url).netloc}\n{body[:MAX_FETCH]}"


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
            "Read a text file; PDF and .docx are converted to text.",
            {"path": S},
            ["path"],
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
            "Open a file, folder or web page for the user with their usual app.",
            {"target": S},
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
