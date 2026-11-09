"""The user's installed AIs: what is on disk, launch info, shortcuts, removal."""

from __future__ import annotations

import json
import time
from pathlib import Path

from datas.catalog import load as load_catalog
from datas.config import home, models_dir
from datas.runtime import downloader

GiB = 2**30


def _meta_path() -> Path:
    return home() / "library.json"


def _meta() -> dict:
    p = _meta_path()
    return json.loads(p.read_text()) if p.exists() else {}


def _save_meta(m: dict) -> None:
    _meta_path().write_text(json.dumps(m, indent=2))


def touch(model_id: str, quant: str) -> None:
    m = _meta()
    m.setdefault(model_id, {})["last_used"] = time.time()
    m[model_id]["quant"] = quant
    _save_meta(m)


def set_shortcut(model_id: str, path: str | None) -> None:
    m = _meta()
    m.setdefault(model_id, {})["shortcut"] = path
    _save_meta(m)


def installed() -> list[dict]:
    """Every installed AI with plain-language info; catalog models first, then custom files."""
    cat = load_catalog()
    meta = _meta()
    out: list[dict] = []
    seen: set[str] = set()
    for m in cat.models:
        files = [f for f in m.files if downloader.is_downloaded(m, f)]
        if not files:
            continue
        seen.add(m.id)
        best = max(files, key=lambda f: f.bytes)
        out.append(
            {
                "model_id": m.id,
                "name": m.name,
                "vendor": m.vendor,
                "vendor_url": m.vendor_url,
                "quant": best.quant,
                "quants": [f.quant for f in files],
                "path": str(downloader.local_path(m, best)),
                "size_gib": round(sum(f.bytes for f in files) / GiB, 1),
                "capabilities": m.capabilities,
                "use_cases": m.use_cases,
                "limits": m.limits,
                "quality_tier": m.quality_tier,
                "last_used": meta.get(m.id, {}).get("last_used"),
                "shortcut": meta.get(m.id, {}).get("shortcut"),
                "custom": False,
            }
        )
    for p in sorted(models_dir().rglob("*.gguf")):
        if p.parent.name in seen or p.name.startswith(
            ("mmproj-", "mtp-", "dflash-", "dspark-", "eagle3-")
        ):
            continue
        if p.parent != models_dir() and p.parent.name in cat.ids():
            continue  # a catalog model's extra quant already covered
        out.append(
            {
                "model_id": f"custom:{p}",
                "name": p.stem,
                "vendor": "unknown (your own file)",
                "vendor_url": None,
                "quant": "",
                "quants": [],
                "path": str(p),
                "size_gib": round(p.stat().st_size / GiB, 1),
                "capabilities": ["chat"],
                "use_cases": ["text"],
                "limits": "A model file you added yourself.",
                "quality_tier": 0,
                "last_used": None,
                "shortcut": None,
                "custom": True,
            }
        )
    out.sort(key=lambda x: x["last_used"] or 0, reverse=True)
    return out


def remove(model_id: str) -> dict:
    """Delete an installed AI's files (user-initiated) and its shortcut."""
    from datas import shortcuts

    cat = load_catalog()
    freed = 0
    if model_id.startswith("custom:"):
        p = Path(model_id[7:])
        if p.exists():
            freed = p.stat().st_size
            p.unlink()
        name = p.stem
    else:
        m = cat.get(model_id)
        d = models_dir() / m.id
        if d.exists():
            for f in d.iterdir():
                freed += f.stat().st_size
                f.unlink()
            d.rmdir()
        name = m.name
    shortcuts.remove(f"{name} (Datas)")
    meta = _meta()
    meta.pop(model_id, None)
    _save_meta(meta)
    return {"removed": model_id, "freed_gib": round(freed / GiB, 1)}
