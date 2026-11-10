"""Server-side chat: system prompt (memory, context files, skill) + optional internet tools.

The UI calls ``POST /api/chat`` and receives Server-Sent Events (SSE): ``token`` deltas,
``tool`` / ``tool_result`` notices when the AI looks something up, then ``done``.

Internet access is a per-session switch. When off, the model gets no tools at all and the
process never opens a network connection on the user's behalf. When on, two read-only tools
exist: ``web_search`` (DuckDuckGo HTML results) and ``fetch_url`` (GET a page as text).
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from datas.chats import LEARN_PROMPT, context_text, read_memory, skill_prompt
from datas.config import Config
from datas.providers import Provider

MAX_TOOL_STEPS = 6
FETCH_CAP = 12_000  # chars of page text handed to a small model


# ---------------------------------------------------------------------------
# Tools (internet only)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Returns titles, links and snippets.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Open a web page (GET) and return its readable text.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", s)
    s = _TAG.sub(" ", s)
    return _WS.sub(" ", html.unescape(s)).strip()


async def web_search(client: httpx.AsyncClient, query: str) -> str:
    r = await client.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (Datas.ar local assistant)"},
    )
    if r.status_code != 200:
        return f"search failed: HTTP {r.status_code}"
    page = r.text
    results = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
        page,
        re.S,
    ):
        href, title, rest = m.group(1), _strip_html(m.group(2)), m.group(3)
        sn = re.search(
            r'class="result__snippet"[^>]*>(.*?)</a>|class="result__snippet"[^>]*>(.*?)</div>',
            rest,
            re.S,
        )
        snippet = _strip_html((sn.group(1) or sn.group(2)) if sn else "")
        # DDG wraps links as /l/?uddg=<encoded>
        u = re.search(r"uddg=([^&]+)", href)
        if u:
            from urllib.parse import unquote

            href = unquote(u.group(1))
        results.append(f"- {title}\n  {href}\n  {snippet}")
        if len(results) >= 6:
            break
    return "\n".join(results) if results else "no results"


async def fetch_url(client: httpx.AsyncClient, url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "only http(s) links"
    try:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Datas.ar local assistant)"})
    except httpx.HTTPError as e:
        return f"could not open the page: {e}"
    ctype = r.headers.get("content-type", "")
    if "html" in ctype:
        text = _strip_html(r.text)
    elif "text" in ctype or "json" in ctype or "xml" in ctype:
        text = r.text
    else:
        return f"({ctype}, {len(r.content)} bytes — not text)"
    return text[:FETCH_CAP] + ("…" if len(text) > FETCH_CAP else "")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

BASE = (
    "You are a helpful assistant running locally on the user's own device through Datas.ar. "
    "Be clear and concise. Spell out acronyms the first time you use them. If you are not sure, say so. "
    "Answer in the user's language."
)


def system_prompt(
    cfg: Config, skill: str | None, internet: bool, lang: str, extra: str | None = None
) -> str:
    parts = [BASE]
    if lang == "es":
        parts.append(
            "The user's interface language is Spanish (Argentina); default to Spanish unless they write in another language."
        )
    sk = skill_prompt(skill)
    if sk == "GUIDE":
        parts.append(
            extra or "You are the Datas guide; the device facts are unavailable right now."
        )
    elif sk:
        parts.append("Current skill: " + sk)
    if internet:
        parts.append(
            "You may use web_search and fetch_url to look things up when the question needs current or specific facts; cite the links you used."
        )
    else:
        parts.append(
            "You have no internet access in this session; say so if asked about very recent events."
        )
    if not cfg.forget:
        mem = read_memory().strip()
        if mem:
            parts.append(
                "Notes about the user from earlier conversations (use them naturally, never recite them):\n"
                + mem[:4000]
            )
    ctx = context_text()
    if ctx:
        parts.append("Documents the user added for you to use:\n" + ctx)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Chat loop with streaming
# ---------------------------------------------------------------------------


@dataclass
class ChatRequest:
    messages: list[dict]
    internet: bool = False
    skill: str | None = None
    lang: str = "en"
    extra: str | None = None  # the guide's live briefing
    temperature: float = 0.7


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def stream_chat(cfg: Config, prov: Provider, req: ChatRequest) -> AsyncIterator[str]:
    messages = [
        {
            "role": "system",
            "content": system_prompt(cfg, req.skill, req.internet, req.lang, req.extra),
        }
    ] + [
        {"role": m["role"], "content": m.get("content", "")}
        for m in req.messages
        if m.get("role") in ("user", "assistant")
    ]
    model = prov.model or "default"
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
        # 1) tool steps (non-streaming) while the model asks for tools
        if req.internet:
            for _ in range(MAX_TOOL_STEPS):
                try:
                    r = await client.post(
                        f"{prov.base_url}/chat/completions",
                        headers=prov.headers(),
                        json={
                            "model": model,
                            "messages": messages,
                            "tools": TOOL_SCHEMAS,
                            "tool_choice": "auto",
                            "temperature": req.temperature,
                        },
                    )
                except httpx.HTTPError as e:
                    yield _sse({"type": "error", "message": f"The AI did not answer: {e}"})
                    return
                if r.status_code >= 400:
                    yield _sse(
                        {
                            "type": "error",
                            "message": f"The AI returned an error ({r.status_code}): {r.text[:300]}",
                        }
                    )
                    return
                msg = r.json()["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                if not calls:
                    # no tools wanted → stream the final answer below
                    break
                messages.append(
                    {"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls}
                )
                for c in calls:
                    fn = c.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield _sse({"type": "tool", "name": name, "args": args})
                    if name == "web_search":
                        result = await web_search(client, str(args.get("query", "")))
                    elif name == "fetch_url":
                        result = await fetch_url(client, str(args.get("url", "")))
                    else:
                        result = f"unknown tool {name}"
                    yield _sse({"type": "tool_result", "name": name, "summary": result[:300]})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": c.get("id", name),
                            "name": name,
                            "content": result,
                        }
                    )
        # 2) final answer, streamed
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": req.temperature,
        }
        try:
            async with client.stream(
                "POST", f"{prov.base_url}/chat/completions", headers=prov.headers(), json=payload
            ) as r:
                if r.status_code >= 400:
                    body = (await r.aread()).decode(errors="replace")
                    yield _sse(
                        {
                            "type": "error",
                            "message": f"The AI returned an error ({r.status_code}): {body[:300]}",
                        }
                    )
                    return
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        j = json.loads(data)
                        delta = j["choices"][0].get("delta", {})
                    except (ValueError, KeyError, IndexError):
                        continue
                    if delta.get("reasoning_content"):
                        yield _sse({"type": "thinking", "text": delta["reasoning_content"]})
                    if delta.get("content"):
                        yield _sse({"type": "token", "text": delta["content"]})
        except httpx.HTTPError as e:
            yield _sse({"type": "error", "message": f"Connection to the AI dropped: {e}"})
            return
    yield _sse({"type": "done"})


async def learn(prov: Provider, messages: list[dict]) -> list[str]:
    """Ask the model for durable facts about the user (used only in 'remember' mode)."""
    convo = [
        {"role": m["role"], "content": m.get("content", "")}
        for m in messages
        if m.get("role") in ("user", "assistant")
    ]
    convo.append({"role": "user", "content": LEARN_PROMPT})
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as client:
        r = await client.post(
            f"{prov.base_url}/chat/completions",
            headers=prov.headers(),
            json={"model": prov.model or "default", "messages": convo, "temperature": 0.1},
        )
        if r.status_code >= 400:
            return []
        text = r.json()["choices"][0]["message"].get("content") or ""
    if "NONE" in text.upper() and len(text) < 20:
        return []
    return [
        ln.lstrip("-• ").strip() for ln in text.splitlines() if ln.strip().startswith(("-", "•"))
    ][:6]
