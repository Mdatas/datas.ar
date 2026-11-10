"""Ready-made helpers ("assistants") and the user's own.

A helper is nothing more than: a name, one line saying what it is for, the instruction given to
the AI, a few example requests, and which export buttons come first (Word, Excel…). Nothing is
hidden: the instruction is shown in the app and can be copied into a helper of your own.

* Built-in helpers: ``catalog.json`` next to this file.
* Your own: ``<data>/assistants/<id>.json`` plus, optionally, a folder of reference documents
  ``<data>/assistants/<id>/`` (a price list, a style guide, templates…). The AI gets the parts
  of those documents that match each question (see ``datas.docs``).
"""

from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from importlib import resources
from pathlib import Path

from datas import docs
from datas.config import home

MINE = {"id": "mine", "name": {"en": "Mine", "es": "Míos"}}
MAX_PROMPT = 8000


@lru_cache(maxsize=1)
def builtin() -> dict:
    p = Path(str(resources.files("datas.assistants").joinpath("catalog.json")))
    return json.loads(p.read_text(encoding="utf-8"))


def user_dir() -> Path:
    p = home() / "assistants"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _custom() -> list[dict]:
    out = []
    for p in sorted(user_dir().glob("*.json")):
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(a, dict) or not a.get("prompt") or not a.get("name"):
            continue
        a["id"] = p.stem
        a["custom"] = True
        a.setdefault("cat", "mine")
        a.setdefault("icon", "star")
        out.append(a)
    return out


def all_assistants() -> list[dict]:
    return _custom() + list(builtin()["assistants"])


def get(aid: str | None) -> dict | None:
    if not aid:
        return None
    for a in all_assistants():
        if a["id"] == aid:
            return a
    return None


def _loc(v, lang: str) -> str:  # noqa: ANN001 - str or {"en":…, "es":…}
    if isinstance(v, dict):
        return v.get(lang) or v.get("en") or next(iter(v.values()), "")
    return v or ""


def public(a: dict, lang: str = "en", with_prompt: bool = False) -> dict:
    st = a.get("starters") or []
    if isinstance(st, dict):
        st = st.get(lang) or st.get("en") or []
    out = {
        "id": a["id"],
        "cat": a.get("cat", "mine"),
        "icon": a.get("icon", "star"),
        "name": _loc(a.get("name"), lang),
        "blurb": _loc(a.get("blurb"), lang),
        "starters": list(st)[:4],
        "export": a.get("export") or ["docx", "pdf"],
        "role": a.get("role"),
        "web": bool(a.get("web")),
        "custom": bool(a.get("custom")),
    }
    if a.get("custom"):
        out["docs"] = list_docs(a["id"])
    if with_prompt:
        out["prompt"] = a["prompt"]
    return out


def listing(lang: str = "en") -> dict:
    items = [public(a, lang) for a in all_assistants()]
    cats = [{"id": c["id"], "name": _loc(c["name"], lang)} for c in builtin()["categories"]]
    if any(i["custom"] for i in items):
        cats.insert(0, {"id": MINE["id"], "name": _loc(MINE["name"], lang)})
    return {"categories": cats, "assistants": items}


def prompt(aid: str | None) -> str:
    a = get(aid)
    return a["prompt"] if a else ""


# ---- the user's own helpers ------------------------------------------------------


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
    return s or "helper"


def save_custom(
    name: str,
    prompt_text: str,
    blurb: str = "",
    starters: list[str] | None = None,
    export: list[str] | None = None,
    aid: str | None = None,
) -> dict:
    """Create (or, with ``aid``, change) a helper of the user's own."""
    name = " ".join(name.split())[:60]
    prompt_text = prompt_text.strip()[:MAX_PROMPT]
    if not name or not prompt_text:
        raise ValueError("a helper needs a name and an instruction")
    if aid:
        aid = Path(aid).name
        if not (user_dir() / f"{aid}.json").exists():
            raise KeyError(aid)
    else:
        aid = f"my-{_slug(name)}-{uuid.uuid4().hex[:4]}"
    data = {
        "name": name,
        "blurb": " ".join(blurb.split())[:160],
        "prompt": prompt_text,
        "starters": [" ".join(s.split())[:140] for s in (starters or []) if s.strip()][:4],
        "export": [e for e in (export or ["docx", "pdf"]) if e in _formats()] or ["docx", "pdf"],
    }
    (user_dir() / f"{aid}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return public(get(aid) or {**data, "id": aid, "custom": True}, with_prompt=True)


def _formats() -> tuple[str, ...]:
    from datas.export import FORMATS

    return FORMATS


def delete_custom(aid: str) -> bool:
    aid = Path(aid).name
    p = user_dir() / f"{aid}.json"
    if not p.exists():
        return False
    p.unlink()
    d = user_dir() / aid
    if d.is_dir():
        for f in d.iterdir():
            if f.is_file():
                f.unlink()
        d.rmdir()
    return True


# ---- reference documents of a custom helper ----------------------------------------


def _doc_dir(aid: str) -> Path:
    aid = Path(aid).name
    if not (user_dir() / f"{aid}.json").exists():
        raise KeyError(aid)
    d = user_dir() / aid
    d.mkdir(exist_ok=True)
    return d


def _safe(name: str) -> str:
    return "".join(c for c in Path(name).name if c.isalnum() or c in " -_.()").strip() or "file.txt"


def add_doc(aid: str, name: str, data: bytes) -> dict:
    """Stores the file and its text (so each chat message does not parse it again).
    Raises ValueError with a plain reason when the file cannot be read as text."""
    text = docs.extract_text(name, data)
    d = _doc_dir(aid)
    safe = _safe(name)
    (d / safe).write_bytes(data)
    (d / (safe + ".datas.txt")).write_text(text, encoding="utf-8")
    return {"name": safe, "bytes": len(data), "chars": len(text)}


def list_docs(aid: str) -> list[dict]:
    d = user_dir() / Path(aid).name
    if not d.is_dir():
        return []
    return [
        {"name": p.name, "bytes": p.stat().st_size}
        for p in sorted(d.iterdir())
        if p.is_file() and not p.name.endswith(".datas.txt")
    ]


def delete_doc(aid: str, name: str) -> bool:
    d = _doc_dir(aid)
    p = d / _safe(name)
    if not p.exists():
        return False
    p.unlink()
    (d / (p.name + ".datas.txt")).unlink(missing_ok=True)
    return True


def docs_text(aid: str | None) -> list[dict]:
    """[{name, text}] for a custom helper's reference documents (empty for built-in ones,
    except the survival helper, which reads the offline survival library)."""
    if not aid:
        return []
    if aid == "survival":
        from datas import survival
        from datas.config import Config

        return survival.docs_text(Config.load().lang)
    d = user_dir() / Path(aid).name
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.datas.txt")):
        try:
            out.append(
                {"name": p.name[: -len(".datas.txt")], "text": p.read_text(encoding="utf-8")}
            )
        except OSError:
            continue
    return out
