"""Learn: a guided library about AI, from first steps to expert material.

Three kinds of content ship with Datas:

* **lessons** — short plain-language texts written for Datas (``lessons.<lang>.md``). They are
  read offline, like everything else in the app.
* a **glossary** of the words the app and the field use.
* a **catalog** of outside courses, videos, reports and official texts (``catalog.json``),
  grouped into paths ("Start here", "Rules and public policy", "Government"…) and marked with
  a level from 1 (new to AI) to 5 (expert). Every address was checked by hand on the date in
  ``checked``; none is generated. Opening one uses the user's own browser.

"Done" marks are kept in ``<home>/learn.json`` — and only in Remember mode.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path

from datas.config import Config, home, write_text_safely

LANGS = ("en", "es")
LESSON = "lesson:"


def _lang(lang: str | None) -> str:
    return lang if lang in LANGS else "en"


def _text(name: str) -> str:
    return (resources.files("datas.learn") / name).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(_text("catalog.json"))


@lru_cache(maxsize=len(LANGS))
def lessons(lang: str = "en") -> dict[str, dict]:
    """Lessons of one language, in file order. A lesson starts with ``=== id | level | minutes``,
    then a ``# Title`` line, then Markdown."""
    out: dict[str, dict] = {}
    cur: dict | None = None
    for line in _text(f"lessons.{_lang(lang)}.md").splitlines():
        if line.startswith("=== "):
            lid, level, minutes = (p.strip() for p in line[4:].split("|"))
            cur = {"id": lid, "level": int(level), "minutes": int(minutes), "title": "", "body": []}
            out[lid] = cur
        elif cur is not None:
            if not cur["title"] and line.startswith("# "):
                cur["title"] = line[2:].strip()
            else:
                cur["body"].append(line)
    for le in out.values():
        le["markdown"] = "\n".join(le.pop("body")).strip()
    return out


def lesson(lesson_id: str, lang: str = "en") -> dict | None:
    le = lessons(_lang(lang)).get(lesson_id)
    return dict(le) if le else None


def known(ref: str) -> bool:
    if ref.startswith(LESSON):
        return ref[len(LESSON) :] in lessons("en")
    return any(i["id"] == ref for i in catalog()["items"])


def urls() -> list[str]:
    return sorted({i["url"] for i in catalog()["items"]})


# ---------------------------------------------------------------------------
# Progress ("done" marks) — Remember mode only
# ---------------------------------------------------------------------------
def _progress_path() -> Path:
    return home() / "learn.json"


def progress(cfg: Config | None = None) -> list[str]:
    if cfg is not None and cfg.forget:
        return []
    try:
        data = json.loads(_progress_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    done = data.get("done") if isinstance(data, dict) else None
    return [str(x) for x in done] if isinstance(done, list) else []


def mark(ref: str, done: bool, cfg: Config) -> bool:
    """Note that a lesson or a link was finished (or undo it). In Forget mode nothing is
    written and the answer is False. Raises KeyError for something Learn does not have."""
    if not known(ref):
        raise KeyError(ref)
    if cfg.forget:
        return False
    cur = [r for r in progress(cfg) if r != ref]
    if done:
        cur.append(ref)
    write_text_safely(_progress_path(), json.dumps({"done": cur}, indent=1))
    return True


# ---------------------------------------------------------------------------
# What the Learn screen shows
# ---------------------------------------------------------------------------
def listing(lang: str = "en", cfg: Config | None = None) -> dict:
    lang = _lang(lang)
    cat = catalog()
    items = {i["id"]: i for i in cat["items"]}
    less = lessons(lang)
    done = set(progress(cfg))

    def entry(ref: str) -> dict:
        if ref.startswith(LESSON):
            le = less[ref[len(LESSON) :]]
            return {
                "ref": ref,
                "type": "lesson",
                "id": le["id"],
                "title": le["title"],
                "level": le["level"],
                "minutes": le["minutes"],
                "done": ref in done,
            }
        i = items[ref]
        return {
            "ref": ref,
            "type": "link",
            "id": i["id"],
            "title": i["title"],
            "by": i["by"],
            "url": i["url"],
            "kind": i["kind"],
            "level": i["level"],
            "minutes": i.get("minutes"),
            "year": i.get("year"),
            "langs": i["lang"],
            "free": i.get("cost") == "free",
            "why": i["why"][lang],
            "done": ref in done,
        }

    paths = [
        {
            "id": p["id"],
            "name": p["name"][lang],
            "blurb": p["blurb"][lang],
            "items": [entry(r) for r in p["items"]],
        }
        for p in cat["paths"]
    ]
    if lang == "es":  # Spanish readers get the Spanish shelf right after the first steps
        paths.sort(key=lambda p: 0 if p["id"] == "start" else 1 if p["id"] == "es" else 2)
    glossary = sorted(
        ({"term": g["term"][lang], "short": g["short"][lang]} for g in cat["glossary"]),
        key=lambda g: g["term"].lower(),
    )
    return {
        "checked": cat["checked"],
        "levels": [{"id": lv["id"], "name": lv["name"][lang]} for lv in cat["levels"]],
        "paths": paths,
        "glossary": glossary,
        "saves_progress": not (cfg is not None and cfg.forget),
        "counts": {"lessons": len(less), "links": len(items), "terms": len(glossary)},
    }
