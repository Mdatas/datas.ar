"""Download every document of the offline survival library and check it.

Run by .github/workflows/library-sources.yml (this needs the open internet). For each entry it
prints the HTTP status, the size, the SHA-256 and what the file says it is (the title line of a
Project Gutenberg text, the first words of a PDF), and compares size and checksum with the ones
pinned in datas/survival/catalog.json. With --pin it writes them in (only for entries that
downloaded and were not pinned yet). Exit code 1 when an entry fails or differs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

import httpx

CATALOG = Path(__file__).resolve().parents[1] / "datas" / "survival" / "catalog.json"
AGENT = "Datas.ar library check (+https://github.com/Mdatas/datas.ar)"


def what_it_says(data: bytes, fmt: str) -> str:
    if fmt == "txt":
        text = data[:6000].decode("utf-8", "replace")
        m = re.search(r"^Title:\s*(.+)$", text, re.M)
        return ("Title: " + m.group(1).strip()) if m else text[:120].replace("\n", " ")
    try:
        from pypdf import PdfReader

        r = PdfReader(io.BytesIO(data))
        first = (r.pages[0].extract_text() or "") if r.pages else ""
        title = (r.metadata or {}).get("/Title") or ""
        return f"{len(r.pages)} pages; title {title!r}; begins {' '.join(first.split())[:140]!r}"
    except Exception as e:  # noqa: BLE001
        return f"not a readable PDF ({type(e).__name__}: {e}); begins {data[:60]!r}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pin", action="store_true")
    a = ap.parse_args()
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    bad = 0
    with httpx.Client(follow_redirects=True, timeout=120, headers={"User-Agent": AGENT}) as c:
        for it in cat["items"]:
            try:
                r = c.get(it["url"])
                data = r.content
                status = r.status_code
                final = str(r.url)
            except httpx.HTTPError as e:
                print(f"FAIL {it['id']}: {type(e).__name__}: {e}", flush=True)
                bad += 1
                continue
            sha = hashlib.sha256(data).hexdigest()
            ok = status == 200 and len(data) > 1000
            if ok and it.get("sha256") and (it["sha256"] != sha or it["size"] != len(data)):
                ok = False
                print(f"DIFF {it['id']}: pinned {it['size']} {it['sha256']}", flush=True)
            print(
                f"{'ok  ' if ok else 'FAIL'} {it['id']}: {status} {len(data)} bytes sha256 {sha}"
                f" type {r.headers.get('content-type')} final {final}\n     {what_it_says(data, it['format'])}",
                flush=True,
            )
            if not ok:
                bad += 1
            elif a.pin and not it.get("sha256"):
                it["size"], it["sha256"] = len(data), sha
    if a.pin:
        CATALOG.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(cat['items']) - bad} of {len(cat['items'])} fine", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
