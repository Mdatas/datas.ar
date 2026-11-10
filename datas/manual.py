"""Everything Datas ships to read: its own documentation, the Learn lessons and the offline
survival guides. The guide helper answers from all of it — with the smallest AI, before any
big one is downloaded, and with no internet.

In an installed copy the documentation is packaged as ``datas/manual/*.md`` (pyproject.toml,
installer/datas.spec); from the source tree it is read from ``docs/`` and ``README.md``.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _docs() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    try:
        packed = resources.files("datas").joinpath("manual")
        files = sorted(
            (p for p in packed.iterdir() if p.name.endswith(".md")), key=lambda p: p.name
        )
        out = [(p.name, p.read_text("utf-8")) for p in files]
    except (FileNotFoundError, NotADirectoryError, OSError):
        out = []
    if not out:  # running from the source tree
        for p in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]:
            if p.is_file():
                out.append((p.name, p.read_text("utf-8")))
    return out


def docs_text(lang: str = "en") -> list[dict]:
    """[{name, text}] the guide may draw from: lessons and survival guides in the person's
    language first, then the English documentation of how Datas works and is built."""
    from datas import survival

    other = "es" if lang != "es" else "en"
    out = []
    for lg in (lang, other):
        name = "lessons.es.md" if lg == "es" else "lessons.en.md"
        try:
            text = resources.files("datas.learn").joinpath(name).read_text("utf-8")
            out.append({"name": f"Datas — Learn lessons ({lg})", "text": text})
        except OSError:
            pass
        out.append({"name": f"Datas — offline survival guides ({lg})", "text": survival.guides(lg)})
    out += [{"name": f"Datas documentation — {n}", "text": t} for n, t in _docs()]
    return out
