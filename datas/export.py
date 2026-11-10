"""Turn an AI answer (Markdown) into real files people use every day.

    Word (.docx) · Excel (.xlsx) · PowerPoint (.pptx) · PDF · web page (.html) · text (.md/.txt)
    and any code block as its own file (.scad, .svg, .html, .py, .csv …).

The AI writes Markdown — the one thing every model, large or small, does reliably — and this
module does the conversion, so exporting does not depend on the model calling tools correctly.
Conventions the assistants are told to follow (see ``datas/assistants``):

* a Markdown table becomes a sheet (Excel) or a table (Word, PowerPoint, PDF); a cell that starts
  with ``=`` is written as a real formula;
* each ``#``/``##`` heading starts a slide; a paragraph starting with ``Notes:`` becomes the
  speaker notes.

Files go to the user's Documents/Datas folder (created on first use).
"""

from __future__ import annotations

import html as _html
import os
import platform
import re
import subprocess
import time
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

from datas.config import home

FORMATS = ("docx", "xlsx", "pptx", "pdf", "html", "md", "txt")
CODE_EXT = {
    "python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts",
    "html": "html", "css": "css", "svg": "svg", "xml": "xml", "json": "json", "yaml": "yaml",
    "yml": "yaml", "toml": "toml", "ini": "ini", "csv": "csv", "tsv": "tsv", "sql": "sql",
    "bash": "sh", "sh": "sh", "shell": "sh", "powershell": "ps1", "ps1": "ps1", "bat": "bat",
    "cmd": "bat", "openscad": "scad", "scad": "scad", "gcode": "gcode", "c": "c", "cpp": "cpp",
    "c++": "cpp", "java": "java", "go": "go", "rust": "rs", "rs": "rs", "kotlin": "kt",
    "swift": "swift", "ruby": "rb", "php": "php", "r": "r", "latex": "tex", "tex": "tex",
    "markdown": "md", "md": "md", "mermaid": "mmd", "dot": "dot", "arduino": "ino",
    "st": "st", "iecst": "st", "ladder": "txt", "dxf": "dxf", "srt": "srt", "vtt": "vtt",
    "dockerfile": "Dockerfile", "nginx": "conf", "text": "txt", "txt": "txt",
}  # fmt: skip


def _md() -> MarkdownIt:
    return MarkdownIt("commonmark", {"breaks": True}).enable(["table", "strikethrough"])


def exports_dir() -> Path:
    """Documents/Datas when the Documents folder exists, else <data>/exports. A copy of Datas
    that keeps its data in a folder of its own (``DATAS_HOME``, portable use and tests) keeps
    its files there too."""
    base: Path | None = None
    if not os.environ.get("DATAS_HOME"):
        try:
            from datas.agents.folders import known_folders

            base = next((Path(f["path"]) for f in known_folders() if f["id"] == "Documents"), None)
        except Exception:  # noqa: BLE001
            base = None
    d = (base / "Datas") if base else (home() / "exports")
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = home() / "exports"
        d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(title: str, fallback: str = "Datas") -> str:
    t = re.sub(r"[#*_`>\[\]]", "", title or "").strip()
    t = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", t)
    t = re.sub(r"\s+", " ", t).strip(" .")[:60].strip()
    return t or fallback


def _target(title: str, ext: str) -> Path:
    d = exports_dir()
    name = safe_name(title)
    p = d / f"{name}.{ext}" if not ext[0].isupper() else d / ext  # e.g. "Dockerfile"
    n = 2
    while p.exists():
        p = d / f"{name} ({n}).{ext}"
        n += 1
    return p


def guess_title(markdown: str) -> str:
    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()
    for line in markdown.splitlines():
        if line.strip():
            return line.strip()[:60]
    return ""


# ---------------------------------------------------------------------------
# a small tree over markdown-it tokens


def _plain(tok: Token | None) -> str:
    """Inline token → text without formatting marks."""
    if tok is None:
        return ""
    out = []
    for c in tok.children or []:
        if c.type in ("text", "code_inline"):
            out.append(c.content)
        elif c.type in ("softbreak", "hardbreak"):
            out.append("\n")
        elif c.type == "image":
            out.append(c.content or "")
    return "".join(out)


def _runs(tok: Token | None) -> list[tuple[str, dict]]:
    """Inline token → [(text, {bold, italic, code, strike, href})]."""
    runs: list[tuple[str, dict]] = []
    if tok is None:
        return runs
    st = {"bold": 0, "italic": 0, "strike": 0}
    href: str | None = None
    for c in tok.children or []:
        if c.type == "strong_open":
            st["bold"] += 1
        elif c.type == "strong_close":
            st["bold"] -= 1
        elif c.type == "em_open":
            st["italic"] += 1
        elif c.type == "em_close":
            st["italic"] -= 1
        elif c.type == "s_open":
            st["strike"] += 1
        elif c.type == "s_close":
            st["strike"] -= 1
        elif c.type == "link_open":
            href = c.attrGet("href")
        elif c.type == "link_close":
            href = None
        elif c.type in ("text", "code_inline", "softbreak", "hardbreak", "image"):
            text = "\n" if c.type in ("softbreak", "hardbreak") else (c.content or "")
            runs.append(
                (
                    text,
                    {
                        "bold": st["bold"] > 0,
                        "italic": st["italic"] > 0,
                        "strike": st["strike"] > 0,
                        "code": c.type == "code_inline",
                        "href": href,
                    },
                )
            )
    return runs


def blocks(markdown: str) -> list[dict]:
    """Flatten Markdown into simple blocks:
    heading{level, inline} · para{inline} · item{level, ordered, number, inline} ·
    code{text, lang} · quote{inline} · table{rows: [[inline…]], header: bool} · rule
    """
    toks = _md().parse(markdown)
    out: list[dict] = []
    list_stack: list[dict] = []
    quote = 0
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if t.type == "heading_open":
            out.append({"type": "heading", "level": int(t.tag[1]), "inline": toks[i + 1]})
            i += 3
            continue
        if t.type in ("bullet_list_open", "ordered_list_open"):
            list_stack.append(
                {"ordered": t.type.startswith("ordered"), "n": int(t.attrGet("start") or 1)}
            )
        elif t.type in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
        elif t.type == "list_item_open":
            cur = list_stack[-1]
            cur["pending"] = True
        elif t.type == "blockquote_open":
            quote += 1
        elif t.type == "blockquote_close":
            quote -= 1
        elif t.type == "paragraph_open":
            inline = toks[i + 1]
            if list_stack:
                cur = list_stack[-1]
                first = cur.pop("pending", False)
                out.append(
                    {
                        "type": "item",
                        "level": len(list_stack) - 1,
                        "ordered": cur["ordered"] and first,
                        "number": cur["n"],
                        "bullet": first,
                        "inline": inline,
                    }
                )
                if first and cur["ordered"]:
                    cur["n"] += 1
            elif quote:
                out.append({"type": "quote", "inline": inline})
            else:
                out.append({"type": "para", "inline": inline})
            i += 3
            continue
        elif t.type in ("fence", "code_block"):
            out.append(
                {
                    "type": "code",
                    "text": t.content.rstrip("\n"),
                    "lang": (t.info or "").strip().split(" ")[0].lower(),
                }
            )
        elif t.type == "hr":
            out.append({"type": "rule"})
        elif t.type == "table_open":
            rows: list[list[Token]] = []
            j = i + 1
            row: list[Token] = []
            while toks[j].type != "table_close":
                if toks[j].type == "tr_open":
                    row = []
                elif toks[j].type == "tr_close":
                    rows.append(row)
                elif toks[j].type == "inline":
                    row.append(toks[j])
                j += 1
            out.append({"type": "table", "rows": rows})
            i = j + 1
            continue
        elif t.type == "html_block":
            out.append({"type": "code", "text": t.content.strip(), "lang": "html"})
        i += 1
    return out


def tables(markdown: str) -> list[tuple[str, list[list[str]]]]:
    """[(title, rows of plain cell text)] — the title is the nearest heading above the table."""
    out = []
    last_heading = ""
    for b in blocks(markdown):
        if b["type"] == "heading":
            last_heading = _plain(b["inline"])
        elif b["type"] == "table":
            out.append((last_heading, [[_plain(c).strip() for c in r] for r in b["rows"]]))
    return out


def code_blocks(markdown: str) -> list[dict]:
    return [{"lang": b["lang"], "text": b["text"]} for b in blocks(markdown) if b["type"] == "code"]


def plain_text(markdown: str) -> str:
    """Readable text without Markdown marks (for .txt and for reading aloud)."""
    lines = []
    for b in blocks(markdown):
        if b["type"] in ("heading", "para", "quote"):
            lines.append(_plain(b["inline"]))
            lines.append("")
        elif b["type"] == "item":
            mark = f"{b['number']}. " if b["ordered"] else ("- " if b["bullet"] else "  ")
            lines.append("  " * b["level"] + mark + _plain(b["inline"]))
        elif b["type"] == "code":
            lines.append(b["text"])
            lines.append("")
        elif b["type"] == "table":
            for r in b["rows"]:
                lines.append(" | ".join(_plain(c).strip() for c in r))
            lines.append("")
    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Word


def to_docx(markdown: str, path: Path, title: str = "") -> Path:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    if title:
        doc.core_properties.title = title
    doc.core_properties.author = "Datas.ar"

    def add_runs(par, inline: Token | None) -> None:  # noqa: ANN001
        for text, f in _runs(inline):
            label = text
            if f["href"] and f["href"] not in text and not f["href"].startswith("#"):
                label = f"{text} ({f['href']})"
            run = par.add_run(label)
            run.bold = f["bold"] or None
            run.italic = f["italic"] or None
            if f["strike"]:
                run.font.strike = True
            if f["code"]:
                run.font.name = "Consolas"
                run.font.size = Pt(10)

    for b in blocks(markdown):
        kind = b["type"]
        if kind == "heading":
            h = doc.add_heading(level=min(b["level"], 4))
            add_runs(h, b["inline"])
        elif kind == "para":
            add_runs(doc.add_paragraph(), b["inline"])
        elif kind == "item":
            level = min(b["level"], 2)
            if b["ordered"]:
                par = doc.add_paragraph()
                par.paragraph_format.left_indent = Pt(18 * (level + 1))
                par.paragraph_format.first_line_indent = Pt(-18)
                par.add_run(f"{b['number']}. ")
            elif b["bullet"]:
                par = doc.add_paragraph(
                    style="List Bullet" + ("" if level == 0 else f" {level + 1}")
                )
            else:  # a second paragraph inside the same list item
                par = doc.add_paragraph()
                par.paragraph_format.left_indent = Pt(18 * (level + 1))
            add_runs(par, b["inline"])
        elif kind == "quote":
            par = doc.add_paragraph(style="Quote")
            add_runs(par, b["inline"])
        elif kind == "code":
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Pt(12)
            run = par.add_run(b["text"])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        elif kind == "rule":
            doc.add_paragraph("―" * 12).alignment = 1
        elif kind == "table":
            rows = b["rows"]
            if not rows:
                continue
            cols = max(len(r) for r in rows)
            t = doc.add_table(rows=len(rows), cols=cols)
            t.style = "Light Grid Accent 1"
            for ri, r in enumerate(rows):
                for ci in range(cols):
                    cell = t.cell(ri, ci)
                    par = cell.paragraphs[0]
                    if ci < len(r):
                        add_runs(par, r[ci])
                    if ri == 0:
                        for run in par.runs:
                            run.bold = True
            doc.add_paragraph()
    doc.save(str(path))
    return path


# ---------------------------------------------------------------------------
# Excel

_CURRENCY = re.compile(r"^(?:US\$|AR\$|U\$S|USD|ARS|EUR|\$|€|£)\s*|\s*(?:USD|ARS|EUR|€|\$)$", re.I)


def to_cell(s: str, lang: str = "en") -> tuple[object, str | None]:
    """Cell text → (value, number format). Formulas stay formulas; only unambiguous numbers
    are converted, with the decimal comma understood for Spanish."""
    t = s.strip()
    if not t:
        return None, None
    if t.startswith("=") and len(t) > 1:
        return t, None
    fmt = None
    body = t
    if body.endswith("%"):
        body, fmt = body[:-1].strip(), "0.00%"
    elif _CURRENCY.search(body):
        body, fmt = _CURRENCY.sub("", body).strip(), "#,##0.00"
    neg = body.startswith("-") or (body.startswith("(") and body.endswith(")"))
    body = body.strip("()-+ ").replace(" ", "").replace(" ", "")
    val: float | int | None = None
    if re.fullmatch(r"\d+", body):
        val = int(body)
    elif lang == "es" and re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", body):
        val = float(body.replace(".", "").replace(",", "."))
    elif lang == "es" and re.fullmatch(r"\d+,\d+", body):
        val = float(body.replace(",", "."))
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", body):
        val = float(body.replace(",", ""))
    elif re.fullmatch(r"\d+\.\d+", body):
        val = float(body)
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", body):  # 1.234,56 in any language
        val = float(body.replace(".", "").replace(",", "."))
    if val is None:
        return t, None
    if isinstance(val, float) and val.is_integer() and fmt is None:
        val = int(val)
    if neg:
        val = -val
    if fmt == "0.00%":
        val = val / 100
    return val, fmt


def to_xlsx(markdown: str, path: Path, title: str = "", lang: str = "en") -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    found = tables(markdown)
    if not found:  # nothing tabular: one column of lines, so the export never fails
        found = [
            (title or "Sheet1", [[ln] for ln in plain_text(markdown).splitlines() if ln.strip()])
        ]
    used: set[str] = set()
    for idx, (name, rows) in enumerate(found, 1):
        base = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:28] or f"Sheet{idx}"
        sheet = base
        k = 2
        while sheet.lower() in used:
            sheet = f"{base[:25]} {k}"
            k += 1
        used.add(sheet.lower())
        ws = wb.create_sheet(title=sheet)
        widths: dict[int, int] = {}
        for ri, r in enumerate(rows, 1):
            for ci, text in enumerate(r, 1):
                val, fmt = (text.strip(), None) if ri == 1 else to_cell(text, lang)
                cell = ws.cell(row=ri, column=ci, value=val)
                if fmt:
                    cell.number_format = fmt
                widths[ci] = max(widths.get(ci, 8), min(60, len(str(text)) + 2))
        if rows:
            for c in ws[1]:
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor="DCEBF8")
                c.alignment = Alignment(vertical="center", wrap_text=True)
            ws.freeze_panes = "A2"
            if len(rows) > 1:
                ws.auto_filter.ref = ws.dimensions
        for ci, w in widths.items():
            ws.column_dimensions[get_column_letter(ci)].width = w
    wb.properties.creator = "Datas.ar"
    if title:
        wb.properties.title = title
    wb.save(str(path))
    return path


# ---------------------------------------------------------------------------
# PowerPoint


def _slides(markdown: str) -> list[dict]:
    """Group blocks into slides: every #/## heading (or a --- rule) starts a new one."""
    slides: list[dict] = []
    cur: dict | None = None
    for b in blocks(markdown):
        if b["type"] == "heading" and b["level"] <= 2:
            cur = {"title": _plain(b["inline"]), "level": b["level"], "body": [], "notes": []}
            slides.append(cur)
            continue
        if b["type"] == "rule":
            cur = None
            continue
        if cur is None:
            cur = {"title": "", "level": 2, "body": [], "notes": []}
            slides.append(cur)
        if b["type"] == "para":
            text = _plain(b["inline"])
            m = re.match(r"^\s*(speaker notes|notes|notas(?: del orador)?)\s*:\s*", text, re.I)
            if m:
                cur["notes"].append(text[m.end() :])
                continue
        cur["body"].append(b)
    return [s for s in slides if s["title"] or s["body"]]


def to_pptx(markdown: str, path: Path, title: str = "") -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    ink, soft, sky = (
        RGBColor(0x0F, 0x27, 0x42),
        RGBColor(0x4A, 0x5F, 0x7A),
        RGBColor(0x74, 0xAC, 0xDF),
    )

    def base_slide(title_text: str, big: bool = False):  # noqa: ANN202
        s = prs.slides.add_slide(blank)
        bar = s.shapes.add_shape(1, 0, 0, Inches(0.28), prs.slide_height)
        bar.fill.solid()
        bar.fill.fore_color.rgb = sky
        bar.line.fill.background()
        tb = s.shapes.add_textbox(
            Inches(0.9), Inches(2.6 if big else 0.5), Inches(11.6), Inches(1.6 if big else 1.1)
        )
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = title_text
        r.font.size = Pt(44 if big else 32)
        r.font.bold = True
        r.font.color.rgb = ink
        return s

    def body_box(s):  # noqa: ANN001, ANN202
        tb = s.shapes.add_textbox(Inches(0.9), Inches(1.7), Inches(11.6), Inches(5.2))
        tb.text_frame.word_wrap = True
        return tb.text_frame

    def add_line(
        tf,
        first: list[bool],
        text: str,
        level: int = 0,
        bullet: str = "",
        size: int = 22,
        bold: bool = False,
        mono: bool = False,
    ) -> None:  # noqa: ANN001
        p = tf.paragraphs[0] if first[0] else tf.add_paragraph()
        first[0] = False
        p.level = min(level, 4)
        r = p.add_run()
        r.text = (bullet + " " if bullet else "") + text
        r.font.size = Pt(size - 2 * min(level, 2))
        r.font.bold = bold
        r.font.color.rgb = ink if level == 0 else soft
        if mono:
            r.font.name = "Consolas"
        p.space_after = Pt(8)

    parts = _slides(markdown)
    if not parts:
        parts = [{"title": title or "Datas", "level": 1, "body": [], "notes": []}]
    for si, sl in enumerate(parts):
        is_title = (
            si == 0
            and sl["level"] == 1
            and len(sl["body"]) <= 2
            and all(b["type"] == "para" for b in sl["body"])
        )
        s = base_slide(sl["title"] or title, big=is_title)
        if is_title:
            if sl["body"]:
                tb = s.shapes.add_textbox(Inches(0.9), Inches(4.3), Inches(11.6), Inches(1.5))
                tb.text_frame.word_wrap = True
                first = [True]
                for b in sl["body"]:
                    add_line(tb.text_frame, first, _plain(b["inline"]), size=24)
        else:
            tf = None
            first = [True]
            lines = 0
            for b in sl["body"]:
                if b["type"] == "table":
                    rows = [[_plain(c).strip() for c in r] for r in b["rows"]]
                    if not rows:
                        continue
                    cols = max(len(r) for r in rows)
                    per = 11
                    for start in range(0, max(1, len(rows) - 1), per - 1):
                        chunk = [rows[0]] + rows[1 + start : start + per] if start else rows[:per]
                        target = s if (start == 0 and lines == 0) else base_slide(sl["title"])
                        top = Inches(1.7)
                        shape = target.shapes.add_table(
                            len(chunk),
                            cols,
                            Inches(0.9),
                            top,
                            Inches(11.6),
                            Inches(0.45 * len(chunk)),
                        )
                        for ri, r in enumerate(chunk):
                            for ci in range(cols):
                                cell = shape.table.cell(ri, ci)
                                cell.text = r[ci] if ci < len(r) else ""
                                for par in cell.text_frame.paragraphs:
                                    for run in par.runs:
                                        run.font.size = Pt(14)
                                        run.font.bold = ri == 0
                    lines += 99
                    continue
                if lines >= 9:  # continue on a new slide instead of overflowing
                    s = base_slide(sl["title"])
                    tf, first, lines = None, [True], 0
                if tf is None:
                    tf = body_box(s)
                if b["type"] == "para":
                    add_line(tf, first, _plain(b["inline"]), size=20)
                elif b["type"] == "item":
                    mark = f"{b['number']}." if b["ordered"] else ("•" if b["bullet"] else "")
                    add_line(tf, first, _plain(b["inline"]), level=b["level"], bullet=mark)
                elif b["type"] == "heading":
                    add_line(tf, first, _plain(b["inline"]), size=24, bold=True)
                elif b["type"] == "quote":
                    add_line(tf, first, "“" + _plain(b["inline"]) + "”", size=22)
                elif b["type"] == "code":
                    for ln in b["text"].splitlines()[:14]:
                        add_line(tf, first, ln, size=14, mono=True)
                        lines += 0.5
                lines += 1
        if sl["notes"]:
            s.notes_slide.notes_text_frame.text = "\n".join(sl["notes"])
    prs.core_properties.title = title or (parts[0]["title"] if parts else "")
    prs.core_properties.author = "Datas.ar"
    prs.save(str(path))
    return path


# ---------------------------------------------------------------------------
# PDF and HTML

_PAGE_CSS = (
    "body{font-family:Asap,'Segoe UI',system-ui,sans-serif;max-width:46rem;margin:2.5rem auto;padding:0 1.2rem;"
    "line-height:1.55;color:#0f2742}h1,h2,h3{line-height:1.2}table{border-collapse:collapse;margin:1rem 0}"
    "th,td{border:1px solid #c9d9ea;padding:.4rem .7rem;text-align:left}th{background:#dcebf8}"
    "pre{background:#f1f6fb;padding:.8rem;border-radius:8px;overflow:auto}code{font-family:Consolas,monospace}"
    "blockquote{border-left:4px solid #74acdf;margin-left:0;padding-left:1rem;color:#4a5f7a}"
)


def to_html(markdown: str, path: Path, title: str = "") -> Path:
    body = _md().render(markdown)
    page = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_html.escape(title or 'Datas')}</title><style>{_PAGE_CSS}</style></head>\n"
        f"<body>\n{body}</body></html>\n"
    )
    path.write_text(page, encoding="utf-8")
    return path


def _fonts_dir() -> Path:
    return Path(__file__).parent / "fonts"


def to_pdf(markdown: str, path: Path, title: str = "") -> Path:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_margins(20, 18, 20)
    pdf.set_auto_page_break(True, margin=18)
    fd = _fonts_dir()
    pdf.add_font("DejaVu", "", str(fd / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(fd / "DejaVuSans-Bold.ttf"))
    pdf.add_font("DejaVu", "I", str(fd / "DejaVuSans-Oblique.ttf"))
    pdf.add_font("DejaVu", "BI", str(fd / "DejaVuSans-BoldOblique.ttf"))
    pdf.add_font("DejaVuMono", "", str(fd / "DejaVuSansMono.ttf"))
    pdf.set_title(title or "Datas")
    pdf.set_creator("Datas.ar")
    pdf.add_page()
    pdf.set_font("DejaVu", size=11)
    body = _md().render(markdown)
    # fpdf2's HTML subset: no <s>, and <pre><code> nests badly → flatten code blocks
    body = re.sub(r"<pre><code[^>]*>", "<pre>", body).replace("</code></pre>", "</pre>")
    body = body.replace("<s>", "").replace("</s>", "")
    # characters DejaVu has no glyph for (emoji) would stop the export: drop them
    body = "".join(ch for ch in body if ord(ch) < 0x1F000 and not 0xFE00 <= ord(ch) <= 0xFE0F)
    from fpdf.fonts import FontFace, TextStyle

    ink, soft = "#0f2742", "#4a5f7a"
    styles = {
        "h1": TextStyle(color=ink, font_style="B", font_size_pt=22, t_margin=6, b_margin=1.2),
        "h2": TextStyle(color=ink, font_style="B", font_size_pt=16, t_margin=6, b_margin=1),
        "h3": TextStyle(color=ink, font_style="B", font_size_pt=13, t_margin=5, b_margin=0.8),
        "h4": TextStyle(color=ink, font_style="B", font_size_pt=11, t_margin=5, b_margin=0.6),
        "blockquote": TextStyle(color=soft, font_style="I", t_margin=3, b_margin=3, l_margin=6),
        "a": FontFace(color="#1c5f9e", emphasis="UNDERLINE"),
        "code": FontFace(family="DejaVuMono"),
        "pre": TextStyle(font_family="DejaVuMono", font_size_pt=9, t_margin=4, l_margin=4),
    }
    pdf.write_html(body, font_family="DejaVu", tag_styles=styles, table_line_separators=True)
    pdf.output(str(path))
    return path


# ---------------------------------------------------------------------------
# entry points


def export(markdown: str, fmt: str, title: str = "", lang: str = "en") -> Path:
    fmt = fmt.lower().lstrip(".")
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")
    title = title or guess_title(markdown) or time.strftime("Datas %Y-%m-%d %H.%M")
    return render(markdown, fmt, _target(title, fmt), title, lang)


def render(markdown: str, fmt: str, path: Path, title: str = "", lang: str = "en") -> Path:
    """Write ``markdown`` as ``fmt`` to exactly ``path`` (used by the agent, which chooses
    where files go inside the folders it was given)."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")
    title = title or guess_title(markdown) or path.stem
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "docx":
        return to_docx(markdown, path, title)
    if fmt == "xlsx":
        return to_xlsx(markdown, path, title, lang)
    if fmt == "pptx":
        return to_pptx(markdown, path, title)
    if fmt == "pdf":
        return to_pdf(markdown, path, title)
    if fmt == "html":
        return to_html(markdown, path, title)
    if fmt == "txt":
        path.write_text(plain_text(markdown), encoding="utf-8")
        return path
    path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return path


def export_code(code: str, lang: str = "", title: str = "") -> Path:
    ext = CODE_EXT.get((lang or "").lower())
    if not ext:
        head = code.lstrip()[:200].lower()
        ext = (
            "html"
            if head.startswith(("<!doctype html", "<html"))
            else ("svg" if head.startswith("<svg") else "txt")
        )
    path = _target(title or "code", ext)
    path.write_text(code.rstrip() + "\n", encoding="utf-8")
    return path


def allowed(path: str | Path) -> Path:
    """Only files Datas itself wrote may be opened through the API."""
    p = Path(path).resolve()
    roots = [exports_dir().resolve(), (home() / "images").resolve(), (home() / "agent").resolve()]
    if not any(p == r or r in p.parents for r in roots) or not p.exists():
        raise PermissionError("not a file made by Datas")
    return p


def open_file(path: str | Path, reveal: bool = False) -> None:
    """Open with the user's default program, or show it in the file manager."""
    p = allowed(path)
    system = platform.system()
    if system == "Windows":
        if reveal:
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            os.startfile(str(p))  # type: ignore[attr-defined]  # noqa: S606
    elif system == "Darwin":
        subprocess.Popen(["open", "-R", str(p)] if reveal else ["open", str(p)])
    else:
        subprocess.Popen(
            ["xdg-open", str(p.parent if reveal else p)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
