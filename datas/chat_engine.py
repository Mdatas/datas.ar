"""Server-side chat: system prompt (helper, memory, documents) + optional internet tools.

The UI calls ``POST /api/chat`` and receives Server-Sent Events (SSE): ``token`` deltas,
``tool`` / ``tool_result`` notices when the AI looks something up, then ``done``.

Internet access is a per-session switch. When off, the model gets no tools at all and the
process never opens a network connection on the user's behalf. When on, two read-only tools
exist: ``web_search`` (DuckDuckGo HTML results) and ``fetch_url`` (GET a page as text); both go
through ``datas.netguard`` so the AI can only reach the public internet.

What the AI is told is assembled here and nowhere else: a short base instruction, the helper
the user picked (``datas.assistants``), the notes file (Remember mode), and the passages of the
user's documents that match the question (``datas.docs``). Long chats are trimmed from the
oldest message so a small model never overflows its working memory.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

from datas import assistants, docs, netguard
from datas.agents.runner import read_written_calls, template_trouble, written_messages
from datas.chats import LEARN_PROMPT, context_docs, read_memory
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


async def web_search(client: httpx.AsyncClient, query: str, allow_local: bool = False) -> str:
    try:
        r = await netguard.aget(
            client, "https://html.duckduckgo.com/html/", allow_local, params={"q": query}
        )
    except netguard.Blocked as e:
        return f"search blocked: {e}"
    except httpx.HTTPError as e:
        return f"search failed: {e}"
    if r.status != 200:
        return f"search failed: HTTP {r.status}"
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


async def fetch_url(client: httpx.AsyncClient, url: str, allow_local: bool = False) -> str:
    try:
        r = await netguard.aget(client, url, allow_local)
    except netguard.Blocked as e:
        return f"not opened: {e}"
    except httpx.HTTPError as e:
        return f"could not open the page: {e}"
    ctype = r.content_type
    if "html" in ctype:
        text = _strip_html(r.text)
    elif "text" in ctype or "json" in ctype or "xml" in ctype:
        text = r.text
    elif "pdf" in ctype or r.url.lower().endswith(".pdf"):
        try:
            text = docs.extract_text("page.pdf", r.body)
        except ValueError as e:
            return f"(a PDF that could not be read: {e})"
    else:
        return f"({ctype}, {len(r.body)} bytes — not text)"
    return text[:FETCH_CAP] + ("…" if len(text) > FETCH_CAP else "")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

BASE = (
    "You are a helpful assistant running locally on the user's own device through Datas.ar. "
    "Be clear and concise. Spell out acronyms the first time you use them. If you are not sure, say so. "
    "Answer in the user's language. Use Markdown when structure helps: headings, lists, tables for "
    "anything tabular, and fenced code blocks for code."
)

CHARS_PER_TOKEN = 3.0  # conservative for Spanish/English text; code and numbers use more tokens
REMOTE_CONTEXT = 32_000  # assumed working memory of a paid service when we cannot ask it


def budgets(ctx_tokens: int) -> tuple[int, int]:
    """(characters for documents, characters for everything sent) for a working memory of
    ``ctx_tokens``. A quarter is left for the answer; documents may take up to 45% of the rest."""
    total = int(max(1024, ctx_tokens) * 0.75 * CHARS_PER_TOKEN)
    return min(120_000, int(total * 0.45)), total


def text_of(content) -> str:  # noqa: ANN001 - str, or OpenAI-style parts when a picture is attached
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict)).strip()
    return str(content or "")


def _size(content) -> int:  # noqa: ANN001
    if isinstance(content, list):  # a picture costs roughly a thousand tokens on small models
        return sum(
            len(str(p.get("text", ""))) if p.get("type") == "text" else 3000
            for p in content
            if isinstance(p, dict)
        )
    return len(str(content or ""))


def fit_history(messages: list[dict], budget_chars: int) -> list[dict]:
    """The newest messages that fit in ``budget_chars`` (always at least the last one), starting
    with a user message as chat templates expect."""
    out: list[dict] = []
    used = 0
    for m in reversed(messages):
        size = _size(m.get("content")) + 16
        if out and used + size > budget_chars:
            break
        out.append(m)
        used += size
    out.reverse()
    while len(out) > 1 and out[0].get("role") != "user":
        out.pop(0)
    return out


def system_prompt(
    cfg: Config,
    skill: str | None,
    internet: bool,
    lang: str,
    extra: str | None = None,
    question: str = "",
    attachments: list[dict] | None = None,
    doc_budget: int = 12_000,
) -> str:
    """``skill`` is the id of the helper in use ("guide" is the built-in Datas guide)."""
    parts = [BASE]
    if lang == "es":
        parts.append(
            "The user's interface language is Spanish (Argentina); default to Spanish unless they write in another language."
        )
    if skill == "guide":
        parts.append(
            extra or "You are the Datas guide; the device facts are unavailable right now."
        )
    else:
        helper = assistants.prompt(skill)
        if helper:
            parts.append("Your role in this chat:\n" + helper)
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
    # documents: attached to this chat first, then the helper's own, then "My documents"
    all_docs = [
        {"name": a.get("name", "file"), "text": a.get("text", "")} for a in (attachments or [])
    ]
    if skill != "guide":
        all_docs += assistants.docs_text(skill)
    else:  # the guide answers from everything Datas ships: lessons, survival, how it is built
        from datas import manual

        all_docs += manual.docs_text(lang)
    try:
        all_docs += context_docs()
    except Exception:  # noqa: BLE001 - an unreadable file must not break the chat
        pass
    block = docs.context_block(question, all_docs, doc_budget)
    if block:
        parts.append(
            "Documents the user gave you (use them; quote the file name when you rely on one):\n"
            + block
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Chat loop with streaming
# ---------------------------------------------------------------------------


@dataclass
class ChatRequest:
    messages: list[dict]
    internet: bool = False
    skill: str | None = None  # helper id (datas.assistants) or "guide"
    lang: str = "en"
    extra: str | None = None  # the guide's live briefing
    temperature: float = 0.7
    attachments: list[dict] = field(default_factory=list)  # [{name, text}] added to this chat
    ctx_tokens: int = 8192  # working memory of the AI that will answer
    allow_local: bool = False  # let the web tools open addresses inside the user's own network


def is_local_url(url: str) -> bool:
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "") in ("127.0.0.1", "localhost", "::1")


def friendly_error(status: int, body: str) -> str:
    """Turn an engine or service error into a sentence the user can act on."""
    low = body.lower()
    if "exceed_context_size" in low or "context size" in low or "context length" in low:
        return (
            "This chat (with its documents) is longer than this AI can keep in mind at once. "
            "Start a new chat, attach fewer documents, or let the AI keep more text in mind "
            "(Settings, The AI)."
        )
    if status in (401, 403):
        return "The service refused the key. Check the API key in Settings → Paid services."
    if status == 404 and "model" in low:
        return "The service does not know that model name. Check it in Settings → Paid services."
    if status == 429:
        return "The service says the limit was reached (too many requests or no credit). Try later."
    if "image" in low and ("not support" in low or "mmproj" in low or "multimodal" in low):
        return (
            "This AI cannot see pictures. In My AIs, start one that understands pictures "
            "(or add one in Add an AI → Understanding pictures)."
        )
    return f"The AI returned an error ({status}): {body[:300]}"


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def build_messages(cfg: Config, req: ChatRequest) -> list[dict]:
    """System prompt + the part of the conversation that fits."""
    convo = [
        {"role": m["role"], "content": m.get("content", "")}
        for m in req.messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    question = next((text_of(m["content"]) for m in reversed(convo) if m["role"] == "user"), "")
    doc_budget, total = budgets(req.ctx_tokens)
    system = system_prompt(
        cfg,
        req.skill,
        req.internet,
        req.lang,
        req.extra,
        question=question,
        attachments=req.attachments,
        doc_budget=doc_budget,
    )
    return [{"role": "system", "content": system}] + fit_history(
        convo, max(2000, total - len(system))
    )


async def stream_chat(cfg: Config, prov: Provider, req: ChatRequest) -> AsyncIterator[str]:
    messages = build_messages(cfg, req)
    model = prov.model or "default"
    # Two connections on purpose: the AI (often on this very device — never through a system
    # proxy) and the web (through the system proxy if there is one).
    async with (
        httpx.AsyncClient(
            timeout=httpx.Timeout(600, connect=30), trust_env=not is_local_url(prov.base_url)
        ) as client,
        httpx.AsyncClient(timeout=httpx.Timeout(40, connect=15)) as web,
    ):
        # 1) tool steps (non-streaming) while the model asks for tools
        written = False  # tools described in plain text (see datas/agents/runner.py)
        if req.internet:
            for _ in range(MAX_TOOL_STEPS):
                body = (
                    {"messages": written_messages(messages, TOOL_SCHEMAS)}
                    if written
                    else {"messages": messages, "tools": TOOL_SCHEMAS, "tool_choice": "auto"}
                )
                try:
                    r = await client.post(
                        f"{prov.base_url}/chat/completions",
                        headers=prov.headers(),
                        json={"model": model, "temperature": req.temperature, **body},
                    )
                except httpx.HTTPError as e:
                    yield _sse({"type": "error", "message": f"The AI did not answer: {e}"})
                    return
                if r.status_code >= 400 and not written and template_trouble(r.text):
                    written = True  # this AI's tool format is not supported by the engine
                    continue
                if r.status_code >= 400:
                    yield _sse(
                        {
                            "type": "error",
                            "message": friendly_error(r.status_code, r.text),
                        }
                    )
                    return
                msg = r.json()["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                if written and not calls:
                    calls, _ = read_written_calls(msg.get("content") or "")
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
                        result = await web_search(web, str(args.get("query", "")), req.allow_local)
                    elif name == "fetch_url":
                        result = await fetch_url(web, str(args.get("url", "")), req.allow_local)
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
            "messages": written_messages(messages, None) if written else messages,
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
                            "message": friendly_error(r.status_code, body),
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
        {"role": m["role"], "content": text_of(m.get("content", ""))}
        for m in messages
        if m.get("role") in ("user", "assistant")
    ]
    convo.append({"role": "user", "content": LEARN_PROMPT})
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(300, connect=30), trust_env=not is_local_url(prov.base_url)
    ) as client:
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
