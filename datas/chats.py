"""Chats, memory notes, context files and skills — all local, all optional.

Two modes, chosen by the user on first run and switchable any time:

* **remember** — conversations are saved under ``<home>/chats``, and a short plain-text
  notes file (``memory.md``) holds things the AI learned about the user. The notes are
  shown to the user, editable, deletable.
* **forget** — nothing here is written. The functions below become no-ops.

Context files (``<home>/context``) are documents the user adds so the AI can use them in every
chat (PDF, Word, Excel, PowerPoint, text…). Ready-made instructions live in ``datas.assistants``.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from datas.config import Config, home

MAX_CONTEXT_CHARS = 60_000  # keep total injected context bounded for small models


# ---- folders -----------------------------------------------------------------


def chats_dir() -> Path:
    p = home() / "chats"
    p.mkdir(parents=True, exist_ok=True)
    return p


def context_dir() -> Path:
    p = home() / "context"
    p.mkdir(parents=True, exist_ok=True)
    return p


def memory_path() -> Path:
    return home() / "memory.md"


# ---- chats --------------------------------------------------------------------


def _title_from(messages: list[dict]) -> str:
    first = next(
        (_text_of(m["content"]) for m in messages if m.get("role") == "user" and m.get("content")),
        "",
    )
    first = " ".join(first.split())
    return (first[:60] + ("…" if len(first) > 60 else "")) or "New chat"


def _tombstones_path() -> Path:
    return chats_dir() / ".deleted.json"


def tombstones() -> dict[str, float]:
    p = _tombstones_path()
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def save_chat(
    cfg: Config,
    chat_id: str | None,
    messages: list[dict],
    model: str,
    model_name: str = "",
    skill: str | None = None,
    attachments: list[dict] | None = None,
    provider: str | None = None,
) -> str | None:
    """Create or update a chat. A title the user typed (rename) is kept; otherwise the title is
    the start of the first question. ``skill`` is the helper (assistant) the chat uses;
    ``attachments`` are the documents added to this chat ({name, text}). Returns the id, or
    None in Forget mode."""
    if cfg.forget:
        return None
    cid = Path(chat_id).name if chat_id else uuid.uuid4().hex[:12]
    p = chats_dir() / f"{cid}.json"
    old: dict = {}
    if p.exists():
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            old = {}
    now = time.time()
    data = {
        "id": cid,
        "title": old["title"] if old.get("title_custom") else _title_from(messages),
        "title_custom": bool(old.get("title_custom")),
        "model": model,
        "model_name": model_name or old.get("model_name", ""),
        "provider": provider if provider is not None else old.get("provider", ""),
        "skill": skill if skill is not None else old.get("skill"),
        "attachments": attachments if attachments is not None else old.get("attachments", []),
        "created": old.get("created", now),
        "updated": now,
        "messages": messages,
    }
    _write_chat(p, data)
    return cid


def _write_chat(p: Path, data: dict) -> None:
    """Write through a temporary file so a crash or a full disk never leaves half a chat."""
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _text_of(content) -> str:  # noqa: ANN001 - str, or OpenAI-style parts when a picture is attached
    if isinstance(content, list):
        return " ".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        ).strip()
    return str(content or "")


def _read(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def list_chats(query: str | None = None) -> list[dict]:
    """Newest first. With ``query``: chats whose title or any message contains every word
    (case-insensitive), each with a short snippet around the first hit."""
    words = [w for w in (query or "").lower().split() if w]
    out = []
    for p in chats_dir().glob("*.json"):
        d = _read(p)
        if not d or "id" not in d:
            continue
        item = {
            "id": d["id"],
            "title": d.get("title", ""),
            "model": d.get("model", ""),
            "model_name": d.get("model_name", ""),
            "skill": d.get("skill"),
            "created": d.get("created", d.get("updated", 0)),
            "updated": d.get("updated", 0),
            "messages": len(d.get("messages", [])),
        }
        if words:
            texts = [d.get("title", "")] + [
                _text_of(m.get("content", "")) for m in d.get("messages", [])
            ]
            hay = "\n".join(texts).lower()
            if not all(w in hay for w in words):
                continue
            hit = next((t for t in texts[1:] if words[0] in t.lower()), "")
            if hit:
                i = hit.lower().index(words[0])
                item["snippet"] = ("…" if i > 40 else "") + " ".join(
                    hit[max(0, i - 40) : i + 80].split()
                )
        out.append(item)
    return sorted(out, key=lambda x: x["updated"], reverse=True)


def load_chat(chat_id: str) -> dict | None:
    p = chats_dir() / f"{Path(chat_id).name}.json"
    return _read(p) if p.exists() else None


def rename_chat(chat_id: str, title: str) -> bool:
    p = chats_dir() / f"{Path(chat_id).name}.json"
    d = _read(p) if p.exists() else None
    title = " ".join(title.split())[:120]
    if not d or not title:
        return False
    d["title"], d["title_custom"], d["updated"] = title, True, time.time()
    _write_chat(p, d)
    return True


def delete_chat(chat_id: str) -> bool:
    p = chats_dir() / f"{Path(chat_id).name}.json"
    if p.exists():
        p.unlink()
        t = tombstones()  # remembered so a linked device does not bring the chat back
        t[Path(chat_id).name] = time.time()
        _tombstones_path().write_text(json.dumps(t), encoding="utf-8")
        return True
    return False


# ---- keeping chats in step between linked devices (datas.link) ---------------------
# Newest change wins, per chat. A deleted chat leaves a "tombstone" (its id and when it was
# deleted) so that another device does not bring it back.


def manifest() -> dict[str, float]:
    """{chat id: when it last changed}."""
    out = {}
    for p in chats_dir().glob("*.json"):
        d = _read(p)
        if d and "id" in d:
            out[str(d["id"])] = float(d.get("updated", 0))
    return out


def apply_tombstones(remote: dict) -> int:
    """Delete local chats that another device deleted after their last change here."""
    mine = tombstones()
    n = 0
    for cid, ts in (remote or {}).items():
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            continue
        cid = Path(str(cid)).name
        p = chats_dir() / f"{cid}.json"
        d = _read(p) if p.exists() else None
        if d is not None and float(d.get("updated", 0)) <= ts:
            p.unlink()
            n += 1
        if ts > mine.get(cid, 0) and (d is None or float(d.get("updated", 0)) <= ts):
            mine[cid] = ts
    _tombstones_path().write_text(json.dumps(mine), encoding="utf-8")
    return n


def apply_remote_chat(d: dict) -> bool:
    """Store a chat received from a linked device if it is newer than what is here."""
    try:
        cid = Path(str(d["id"])).name
        updated = float(d.get("updated", 0))
    except (KeyError, TypeError, ValueError):
        return False
    if not cid or not isinstance(d.get("messages"), list):
        return False
    if updated <= tombstones().get(cid, 0):
        return False  # deleted here after that version
    p = chats_dir() / f"{cid}.json"
    old = _read(p) if p.exists() else None
    if old and float(old.get("updated", 0)) >= updated:
        return False
    _write_chat(p, d)
    return True


def wipe_everything() -> dict:
    """The 'forget me' button: chats, notes and context files."""
    n = 0
    t = tombstones()
    for p in chats_dir().glob("*.json"):
        t[p.stem] = time.time()
        p.unlink()
        n += 1
    _tombstones_path().write_text(json.dumps(t), encoding="utf-8")
    if memory_path().exists():
        memory_path().unlink()
    for p in list(context_dir().iterdir()) + list(_cache_dir().iterdir()):
        if p.is_file():
            p.unlink()
    return {"chats_deleted": n}


# ---- memory notes -------------------------------------------------------------


def read_memory() -> str:
    p = memory_path()
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_memory(text: str) -> None:
    memory_path().write_text(text, encoding="utf-8")


def append_memory(cfg: Config, lines: list[str]) -> int:
    if cfg.forget or not lines:
        return 0
    existing = read_memory()
    new = [ln.strip() for ln in lines if ln.strip() and ln.strip() not in existing]
    if not new:
        return 0
    stamp = time.strftime("%Y-%m-%d")
    write_memory(
        existing.rstrip()
        + ("\n" if existing else "")
        + "\n".join(f"- {ln} ({stamp})" for ln in new)
        + "\n"
    )
    return len(new)


LEARN_PROMPT = (
    "From the conversation above, list up to 6 short, durable facts or preferences about the USER that "
    "would help a future assistant (name, language, interests, how they like answers, ongoing projects). "
    "Only things the user actually said. One per line, starting with '- '. If there is nothing, answer 'NONE'."
)


# ---- context files --------------------------------------------------------------
# Documents the user wants the AI to use in every chat. The original file is kept as is; its
# text is extracted once (PDF, Word, Excel, PowerPoint, web page, text) and cached beside it.


def _cache_dir() -> Path:
    p = context_dir() / ".text"
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_context() -> list[dict]:
    from datas import docs

    out = []
    for p in sorted(context_dir().iterdir()):
        if p.is_file():
            out.append({"name": p.name, "bytes": p.stat().st_size, "text": docs.supported(p.name)})
    return out


def add_context(name: str, data: bytes) -> dict:
    """Raises ValueError (plain reason) when the file cannot be read as text."""
    from datas import docs

    safe = "".join(c for c in Path(name).name if c.isalnum() or c in " -_.()").strip() or "file.txt"
    text = docs.extract_text(safe, data)
    p = context_dir() / safe
    p.write_bytes(data)
    (_cache_dir() / (safe + ".txt")).write_text(text, encoding="utf-8")
    return {"name": safe, "bytes": len(data), "chars": len(text)}


def delete_context(name: str) -> bool:
    p = context_dir() / Path(name).name
    if p.exists() and p.is_file():
        p.unlink()
        (_cache_dir() / (p.name + ".txt")).unlink(missing_ok=True)
        return True
    return False


def context_docs() -> list[dict]:
    """[{name, text}] for every readable context file (extracting any not cached yet)."""
    from datas import docs

    out = []
    for p in sorted(context_dir().iterdir()):
        if not p.is_file() or not docs.supported(p.name):
            continue
        cache = _cache_dir() / (p.name + ".txt")
        try:
            if cache.exists() and cache.stat().st_mtime >= p.stat().st_mtime:
                text = cache.read_text(encoding="utf-8")
            else:
                text = docs.extract_text(p.name, p.read_bytes())
                cache.write_text(text, encoding="utf-8")
        except (ValueError, OSError):
            continue
        if text.strip():
            out.append({"name": p.name, "text": text})
    return out


def context_text(limit: int = MAX_CONTEXT_CHARS) -> str:
    """All context documents as one block, cut fairly to ``limit`` characters."""
    files = context_docs()
    if not files:
        return ""
    per = max(2000, limit // len(files))
    parts = []
    for f in files:
        t = f["text"]
        if len(t) > per:
            t = t[:per] + "\n…(truncated)"
        parts.append(f"### File: {f['name']}\n{t}")
    return "\n\n".join(parts)
