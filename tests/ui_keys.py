"""Find every text key the window's scripts ask for (``t("key")``), for the tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "datas" / "server" / "ui"
SCRIPTS = ("app.js", "chat.js", "screens.js")
LITERAL = re.compile(r'"([a-z][a-z0-9_]*)"')


def _calls(src: str):
    """The text between the brackets of each ``t( … )`` call."""
    for m in re.finditer(r"(?<![A-Za-z0-9_.$])t\(", src):
        depth, i = 1, m.end()
        while i < len(src) and depth:
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
        yield src[m.end() : i - 1]


def used() -> tuple[set[str], set[str]]:
    """(exact keys, prefixes such as ``nav_`` that are completed while the app runs)."""
    keys: set[str] = set()
    prefixes: set[str] = set()
    for name in SCRIPTS:
        path = UI / name
        if not path.exists():
            continue
        for call in _calls(path.read_text(encoding="utf-8")):
            head = call.split(",", 1)[0] if "{" in call else call   # skip the {name: value} part
            for lit in LITERAL.findall(head):
                (prefixes if lit.endswith("_") else keys).add(lit)
    return keys, prefixes


def dictionary() -> dict[str, dict[str, str]]:
    src = (UI / "i18n.js").read_text(encoding="utf-8")
    start = src.index("{", src.index("const I18N"))
    return json.loads(src[start : src.rindex("}") + 1])


if __name__ == "__main__":
    k, p = used()
    print(len(k), "keys;", "prefixes:", " ".join(sorted(p)))
    print(" ".join(sorted(k)))
