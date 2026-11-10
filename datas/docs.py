"""Reading the user's documents, and picking the parts that matter for a question.

``extract_text`` turns the everyday formats into plain text: PDF, Word (.docx), Excel (.xlsx),
PowerPoint (.pptx), web pages and any text file. ``context_block`` then decides what goes to
the AI: everything when it fits, otherwise the passages that best match the question
(BM25 keyword ranking — no extra model, works offline, fast on any device).
"""

from __future__ import annotations

import html
import io
import math
import re
from collections import Counter
from pathlib import Path

MAX_DOC_CHARS = 2_000_000
TEXT_SUFFIXES = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".log", ".ini", ".toml",
    ".py", ".js", ".ts", ".css", ".sql", ".sh", ".ps1", ".bat", ".tex", ".srt", ".vtt", ".scad",
    ".svg", ".c", ".cpp", ".h", ".java", ".go", ".rs", ".rb", ".php", ".kt", ".swift", ".r",
}  # fmt: skip
RICH_SUFFIXES = {".pdf", ".docx", ".xlsx", ".xlsm", ".pptx", ".html", ".htm"}
SUPPORTED = TEXT_SUFFIXES | RICH_SUFFIXES


def supported(name: str) -> bool:
    return Path(name).suffix.lower() in SUPPORTED


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    out = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            out.append(f"[page {i}]\n{t}")
    if not out:
        raise ValueError(
            "this PDF has no selectable text (it is probably a scan); a picture-reading AI is needed"
        )
    return "\n\n".join(out)


def _docx(data: bytes) -> str:
    from docx import Document

    d = Document(io.BytesIO(data))
    out = []
    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        style = (p.style.name or "").lower() if p.style is not None else ""
        if style.startswith("heading"):
            level = "".join(ch for ch in style if ch.isdigit()) or "1"
            out.append("#" * min(6, int(level)) + " " + t)
        elif "list" in style:
            out.append("- " + t)
        else:
            out.append(t)
    for table in d.tables:
        for row in table.rows:
            out.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(out)


def _xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    out = []
    for ws in wb.worksheets:
        out.append(f"## Sheet: {ws.title}")
        n = 0
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            while cells and cells[-1] == "":
                cells.pop()
            if cells:
                out.append(" | ".join(cells))
                n += 1
            if n >= 5000:
                out.append("…(more rows not shown)")
                break
    return "\n".join(out)


def _pptx(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    out = []
    for i, slide in enumerate(prs.slides, 1):
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None else ""
        out.append(f"## Slide {i}" + (f": {title}" if title else ""))
        for shape in slide.shapes:
            if shape.has_text_frame and shape != slide.shapes.title:
                for para in shape.text_frame.paragraphs:
                    t = "".join(r.text for r in para.runs).strip()
                    if t:
                        out.append("- " + t)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    out.append(" | ".join(c.text.strip() for c in row.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                out.append("Notes: " + notes)
    return "\n".join(out)


def _html(data: bytes) -> str:
    s = data.decode("utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", s)
    s = re.sub(r"(?i)<(br|/p|/div|/h[1-6]|/li|/tr)[^>]*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", s)).strip()


def extract_text(name: str, data: bytes) -> str:
    """Plain text of a document. Raises ValueError with a plain-language reason when it cannot."""
    ext = Path(name).suffix.lower()
    try:
        if ext == ".pdf":
            text = _pdf(data)
        elif ext == ".docx":
            text = _docx(data)
        elif ext in (".xlsx", ".xlsm"):
            text = _xlsx(data)
        elif ext == ".pptx":
            text = _pptx(data)
        elif ext in (".html", ".htm"):
            text = _html(data)
        elif ext in TEXT_SUFFIXES or not ext:
            if b"\x00" in data[:4096]:
                raise ValueError("this looks like a program or media file, not a text document")
            text = data.decode("utf-8", errors="replace")
        elif ext in (".doc", ".xls", ".ppt"):
            raise ValueError(
                f"old Office format ({ext}): open it and save it as {ext}x, then add it again"
            )
        else:
            raise ValueError(f"files of type {ext} cannot be read as text")
    except ValueError:
        raise
    except Exception as e:  # noqa: BLE001 - damaged or password-protected files
        raise ValueError(f"could not read {name}: {type(e).__name__}: {e}") from e
    text = text.replace("\r\n", "\n").strip()
    if len(text) > MAX_DOC_CHARS:
        text = text[:MAX_DOC_CHARS] + "\n…(document cut here: too long)"
    return text


# ---------------------------------------------------------------------------
# picking passages


_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(s: str) -> list[str]:
    return [w for w in _WORD.findall(s.lower()) if len(w) > 1]


def chunk(text: str, size: int = 1400, overlap: int = 200) -> list[str]:
    """Split on paragraph boundaries into pieces of about ``size`` characters."""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > size:  # a single huge paragraph: hard split
            head, p = p[:size], p[size - overlap :]
            if cur:
                out.append(cur)
                cur = ""
            out.append(head)
        if len(cur) + len(p) + 2 > size and cur:
            out.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur.strip():
        out.append(cur)
    return out


def select(question: str, docs: list[dict], budget_chars: int) -> list[dict]:
    """``docs``: [{name, text}] → [{name, part, parts, text}] within ``budget_chars``.

    Everything is returned whole when it fits. Otherwise passages are ranked against the
    question with BM25 and taken best-first; with no word in common, the start of each document
    is used so the AI at least knows what it is looking at.
    """
    docs = [d for d in docs if d.get("text")]
    if not docs:
        return []
    if sum(len(d["text"]) for d in docs) <= budget_chars:
        return [{"name": d["name"], "part": 1, "parts": 1, "text": d["text"]} for d in docs]
    pieces: list[dict] = []
    for di, d in enumerate(docs):
        cs = chunk(d["text"])
        for ci, c in enumerate(cs):
            pieces.append(
                {"name": d["name"], "doc": di, "part": ci + 1, "parts": len(cs), "text": c}
            )
    toks = [_tokens(p["text"]) for p in pieces]
    n = len(pieces)
    avg = sum(len(t) for t in toks) / max(1, n)
    df: Counter[str] = Counter()
    for t in toks:
        df.update(set(t))
    q = _tokens(question)
    scores = []
    for t in toks:
        tf = Counter(t)
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * 2.5 / (tf[w] + 1.5 * (0.25 + 0.75 * len(t) / max(1.0, avg)))
        scores.append(s)
    order = sorted(range(n), key=lambda i: (-scores[i], pieces[i]["doc"], pieces[i]["part"]))
    if not any(scores):  # nothing matches: document openings, round-robin
        order = sorted(range(n), key=lambda i: (pieces[i]["part"], pieces[i]["doc"]))
    chosen: list[int] = []
    used = 0
    for i in order:
        size = len(pieces[i]["text"])
        if used + size > budget_chars:
            continue
        chosen.append(i)
        used += size
        if used >= budget_chars * 0.95:
            break
    chosen.sort(key=lambda i: (pieces[i]["doc"], pieces[i]["part"]))
    return [{k: pieces[i][k] for k in ("name", "part", "parts", "text")} for i in chosen]


def context_block(question: str, docs: list[dict], budget_chars: int) -> str:
    """The text handed to the AI, with each passage labelled by file (and part when cut)."""
    picked = select(question, docs, budget_chars)
    if not picked:
        return ""
    whole = all(p["parts"] == 1 for p in picked)
    out = []
    for p in picked:
        label = f"### File: {p['name']}" + (
            "" if p["parts"] == 1 else f" (part {p['part']} of {p['parts']})"
        )
        out.append(f"{label}\n{p['text']}")
    note = (
        ""
        if whole
        else "\n\n(Only the passages that best match the question are shown; the documents are longer. "
        "Say so if the answer may be in a part you cannot see.)"
    )
    return "\n\n".join(out) + note
