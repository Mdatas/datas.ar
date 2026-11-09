"""Chats, memory notes, context files and skills — all local, all optional.

Two modes, chosen by the user on first run and switchable any time:

* **remember** — conversations are saved under ``<home>/chats``, and a short plain-text
  notes file (``memory.md``) holds things the AI learned about the user. The notes are
  shown to the user, editable, deletable.
* **forget** — nothing here is written. The functions below become no-ops.

Context files (``<home>/context``) are documents the user adds so the AI can use them;
skills are ready-made instructions ("summarize", "translate", …).
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


def save_chat(cfg: Config, chat_id: str | None, messages: list[dict], model: str) -> str | None:
    if cfg.forget:
        return None
    cid = chat_id or uuid.uuid4().hex[:12]
    title = next(
        (m["content"][:60] for m in messages if m.get("role") == "user" and m.get("content")),
        "chat",
    )
    (chats_dir() / f"{cid}.json").write_text(
        json.dumps(
            {
                "id": cid,
                "title": title,
                "model": model,
                "updated": time.time(),
                "messages": messages,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return cid


def list_chats() -> list[dict]:
    out = []
    for p in chats_dir().glob("*.json"):
        try:
            d = json.loads(p.read_text())
            out.append(
                {
                    "id": d["id"],
                    "title": d.get("title", ""),
                    "model": d.get("model", ""),
                    "updated": d.get("updated", 0),
                    "messages": len(d.get("messages", [])),
                }
            )
        except Exception:
            continue
    return sorted(out, key=lambda x: x["updated"], reverse=True)


def load_chat(chat_id: str) -> dict | None:
    p = chats_dir() / f"{chat_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def delete_chat(chat_id: str) -> bool:
    p = chats_dir() / f"{chat_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def wipe_everything() -> dict:
    """The 'forget me' button: chats, notes and context files."""
    n = 0
    for p in chats_dir().glob("*.json"):
        p.unlink()
        n += 1
    if memory_path().exists():
        memory_path().unlink()
    for p in context_dir().iterdir():
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

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".py",
    ".js",
    ".html",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
    ".ini",
    ".toml",
}


def list_context() -> list[dict]:
    out = []
    for p in sorted(context_dir().iterdir()):
        if p.is_file():
            out.append(
                {
                    "name": p.name,
                    "bytes": p.stat().st_size,
                    "text": p.suffix.lower() in TEXT_SUFFIXES,
                }
            )
    return out


def add_context(name: str, data: bytes) -> dict:
    safe = "".join(c for c in name if c.isalnum() or c in " -_.()").strip() or "file.txt"
    p = context_dir() / safe
    p.write_bytes(data)
    return {"name": safe, "bytes": len(data)}


def delete_context(name: str) -> bool:
    p = context_dir() / name
    if p.exists() and p.is_file():
        p.unlink()
        return True
    return False


def context_text(limit: int = MAX_CONTEXT_CHARS) -> str:
    """Concatenate text context files (truncated fairly) for the system prompt."""
    files = [
        p
        for p in sorted(context_dir().iterdir())
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
    ]
    if not files:
        return ""
    per = max(2000, limit // len(files))
    parts = []
    for p in files:
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if len(t) > per:
            t = t[:per] + "\n…(truncated)"
        parts.append(f"### File: {p.name}\n{t}")
    return "\n\n".join(parts)


# ---- skills -----------------------------------------------------------------------

SKILLS: list[dict] = [
    {
        "id": "plain",
        "en": "Explain simply",
        "es": "Explicar fácil",
        "prompt": "Explain things in plain language for someone with no technical background. Short sentences. Spell out every acronym the first time.",
    },
    {
        "id": "summarize",
        "en": "Summarize",
        "es": "Resumir",
        "prompt": "Summarize the text the user gives you: first a one-sentence takeaway, then 3–6 bullets of the key points. Keep the original language.",
    },
    {
        "id": "email",
        "en": "Write an email",
        "es": "Escribir un email",
        "prompt": "Draft emails: clear subject line, polite and concise body, one call to action. Ask for missing details only if essential.",
    },
    {
        "id": "translate",
        "en": "Translate",
        "es": "Traducir",
        "prompt": "Translate what the user gives you. If they do not say the target language, ask once. Keep tone and formatting.",
    },
    {
        "id": "proofread",
        "en": "Fix my writing",
        "es": "Corregir mi texto",
        "prompt": "Correct spelling, grammar and clarity without changing the meaning or voice. Show the corrected text, then list the main changes briefly.",
    },
    {
        "id": "teach",
        "en": "Teach me",
        "es": "Enseñame",
        "prompt": "Act as a patient tutor: check what the user already knows, explain step by step with one example, then ask one short question to confirm understanding.",
    },
    {
        "id": "code",
        "en": "Help me code",
        "es": "Ayudame a programar",
        "prompt": "Help with programming: give working code with brief comments, explain what it does in two sentences, mention how to run it.",
    },
    {
        "id": "plan",
        "en": "Make a plan",
        "es": "Armar un plan",
        "prompt": "Turn the user's goal into a realistic step-by-step plan with rough timing and the first concrete action to take today.",
    },
]


def skill_prompt(skill_id: str | None) -> str:
    for s in SKILLS:
        if s["id"] == skill_id:
            return s["prompt"]
    return ""
