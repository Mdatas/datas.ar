"""Offline survival: guides and documents kept on this device for when there is no internet.

Two parts, both readable with no AI at all and searchable by the smallest one:

* **Datas' own guides** (``guides.en.md``, ``guides.es.md``), shipped with the program: the first
  hours of a crisis, water, food, electricity, staying connected, travel, living on your own
  means for a long time, and above all doing it together with the people around you. Each
  section ends with the sources its figures come from.
* **A library to keep** (``catalog.json``): public-domain and openly shared documents fetched
  once from their own publishers — FEMA, CDC, WHO, Hesperian, Project Gutenberg… — each checked
  against the size and SHA-256 recorded when the list was verified
  (``scripts/check_survival.py``). Their text is extracted once and kept next to them, so the
  "survival" helper can answer from it with no internet.
"""

from __future__ import annotations

import json
import re
import threading
from importlib import resources
from pathlib import Path

from datas.config import home
from datas.words import Problem

_lock = threading.Lock()
ASK_KINDS = {"guide", "sheet", "chapter", "book"}  # what the helper reads; novels are not


def catalog() -> dict:
    return json.loads(resources.files("datas.survival").joinpath("catalog.json").read_text("utf-8"))


def folder() -> Path:
    return home() / "survival"


def guides(lang: str = "en") -> str:
    name = "guides.es.md" if lang == "es" else "guides.en.md"
    return resources.files("datas.survival").joinpath(name).read_text("utf-8")


def guide_sections(lang: str = "en") -> list[dict]:
    """The guides cut at their ``## `` headings: [{id, title, text}]."""
    out = []
    for block in re.split(r"(?m)^## ", guides(lang))[1:]:
        title, _, body = block.partition("\n")
        sid = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        m = re.match(r"\s*<!--\s*id:\s*([a-z-]+)\s*-->", body)
        if m:  # a stable id written in the file, the same in both languages
            sid, body = m.group(1), body[m.end() :]
        out.append({"id": sid, "title": title.strip(), "text": body.strip()})
    return out


def _item(item_id: str) -> dict:
    for it in catalog()["items"]:
        if it["id"] == item_id:
            return it
    raise Problem("That document is not in the library.")


def _paths(it: dict) -> tuple[Path, Path]:
    f = folder() / f"{it['id']}.{it['format']}"
    return f, f.with_name(f.name + ".datas.txt")


def have(it: dict) -> bool:
    return _paths(it)[0].is_file()


def state(lang: str = "en") -> dict:
    cat = catalog()
    items = []
    for it in cat["items"]:
        if not it.get("sha256"):
            continue  # not verified yet: never offered
        f, _ = _paths(it)
        items.append(
            {
                **{k: it[k] for k in ("id", "title", "by", "topic", "lang", "kind", "page")},
                **{k: it[k] for k in ("format", "license", "license_url", "size")},
                "why": it["why"].get(lang) or it["why"]["en"],
                "have": f.is_file(),
            }
        )
    kept = [i for i in items if i["have"]]
    return {
        "topics": [{"id": t["id"], "name": t["name"].get(lang, t["name"]["en"])} for t in cat["topics"]],
        "items": items,
        "checked": cat.get("checked"),
        "guides": guide_sections(lang),
        "kept": len(kept),
        "kept_bytes": sum(i["size"] or 0 for i in kept),
        "missing_bytes": sum(i["size"] or 0 for i in items if not i["have"]),
    }


def fetch(item_id: str, progress=None, source: str | None = None) -> dict:  # noqa: ANN001
    """Download one document from its publisher, check it, keep its text for the helper.
    ``source`` replaces the address in the tests."""
    import httpx

    from datas import docs
    from datas.config import write_text_safely
    from datas.runtime.llamacpp import _download

    it = _item(item_id)
    if not it.get("sha256"):
        raise Problem("That document has not been checked yet, so it is not offered.")
    f, txt = _paths(it)
    with _lock:
        if not f.is_file():
            try:
                with httpx.Client(
                    follow_redirects=True,
                    timeout=httpx.Timeout(60, read=120),
                    headers={"User-Agent": "Datas.ar (+https://github.com/Mdatas/datas.ar)"},
                ) as c:
                    _download(source or it["url"], f, c, progress, "sha256:" + it["sha256"])
            except ValueError as e:
                raise Problem(
                    "The file that arrived from {site} is not the one Datas checked, so it was "
                    "not kept. The publisher may have changed it; open its page instead: {page}",
                    site=_site(it["url"]),
                    page=it["page"],
                ) from e
            except (httpx.HTTPError, OSError) as e:
                raise Problem(
                    "Could not download it from {site} ({why}). Check the internet connection, "
                    "or open its page: {page}",
                    site=_site(it["url"]),
                    why=type(e).__name__,
                    page=it["page"],
                ) from e
        if not txt.is_file():
            text = docs.extract_text(f.name, f.read_bytes())
            write_text_safely(txt, text)
    return {"id": it["id"], "bytes": f.stat().st_size}


def fetch_all(lang: str = "en", progress=None) -> dict:  # noqa: ANN001
    """Every verified document not kept yet: those in ``lang`` first. One failure does not stop
    the others; their names come back in ``failed``."""
    todo = [i for i in state(lang)["items"] if not i["have"]]
    todo.sort(key=lambda i: (i["lang"] != lang, i["kind"] == "reading"))
    total = sum(i["size"] or 0 for i in todo) or 1
    done, got, failed = 0, [], []
    for it in todo:
        base = done

        def step(d, _t, base=base):  # noqa: ANN001
            if progress:
                progress(base + d, total)

        try:
            fetch(it["id"], step)
            got.append(it["id"])
        except Problem:
            failed.append(it["title"])
        done += it["size"] or 0
    return {"got": got, "failed": failed}


def remove(item_id: str) -> bool:
    it = _item(item_id)
    gone = False
    for p in _paths(it):
        if p.is_file():
            p.unlink()
            gone = True
    return gone


def file_of(item_id: str) -> Path:
    f, _ = _paths(_item(item_id))
    if not f.is_file():
        raise Problem("That document is not on this device yet.")
    return f


def docs_text(lang: str = "en") -> list[dict]:
    """[{name, text}] for the survival helper: Datas' guides in both languages, then every kept
    document that is a guide, a sheet, a chapter or a how-to book (not the novels)."""
    out = [
        {"name": "Datas — offline survival guides (English)", "text": guides("en")},
        {"name": "Datas — guías de supervivencia sin conexión (español)", "text": guides("es")},
    ]
    if lang == "es":
        out.reverse()
    for it in catalog()["items"]:
        if it.get("kind") not in ASK_KINDS:
            continue
        _, txt = _paths(it)
        if txt.is_file():
            try:
                out.append({"name": f"{it['title']} — {it['by']}", "text": txt.read_text("utf-8")})
            except OSError:
                continue
    return out


def _site(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).hostname or url
