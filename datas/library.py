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
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return d if isinstance(d, dict) else {}
    except (ValueError, OSError):
        return {}


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


USE_PLAIN = {
    "text": ("chat, writing, summaries, translation", "chat, escritura, resúmenes, traducción"),
    "images": ("understanding pictures and documents", "entender imágenes y documentos"),
    "coding": ("programming", "programar"),
    "agents": ("doing tasks step by step with tools", "hacer tareas paso a paso con herramientas"),
    "math": ("solving math problems", "resolver problemas de matemática"),
    "legal": ("reading and drafting legal text", "leer y redactar textos legales"),
    "medical": ("medical text and medical images", "texto e imágenes médicas"),
}


def details(core, lang: str = "en") -> list[dict]:  # noqa: ANN001 - Datas orchestrator
    """Installed AIs with what a person wants to know: what it is good for, what it is not,
    who made it, what it costs this device, and lighter / stronger versions that exist."""
    from datas.recommend.engine import evaluate
    from datas.words import tr

    es = 1 if lang == "es" else 0
    cat = core.catalog
    rec = core.recommendation()
    budget, ctx = rec.budget, rec.context
    fit_ids = {c.model_id: c for c in rec.fits}
    out = []
    for it in installed():
        it["limits"] = tr(it.get("limits") or "", lang)
        if it["custom"]:
            it.update({"good_for": "", "resources": None, "versions": [], "alternatives": {}})
            out.append(it)
            continue
        m = cat.get(it["model_id"])
        f = m.file(it["quant"])
        c = evaluate(m, f, budget, ctx)
        p = c.plain(lang)
        it.update(
            {
                "family": m.family,
                "role": m.role,
                "license": p["license"],
                "model_page": p["model_page"],
                "comparable": p["comparable"],
                "kind": p["kind"],
                "finetune_of": m.finetune_of,
                "good_for": ", ".join(USE_PLAIN.get(u, (u, u))[es] for u in m.use_cases),
                "resources": {
                    "disk_gib": it["size_gib"],
                    "memory_gib": round(c.need.total / GiB, 1),
                    "fits": c.fits,
                    "fit_level": c.fit_level,
                    "speed_class": c.speed_class,
                    "placement": c.placement,
                    "where": p["where"],
                    "speed": p["speed"],
                    "context": ctx,
                    "budget_gib": round(budget.total_budget / GiB, 1),
                },
            }
        )
        # same model, other compression levels (quants)
        versions = []
        for of in m.files:
            if of.quant == it["quant"]:
                continue
            oc = evaluate(m, of, budget, ctx)
            versions.append(
                {
                    "kind": "quant",
                    "model_id": m.id,
                    "name": f"{m.name} ({of.quant})",
                    "quant": of.quant,
                    "relation": "lighter" if of.bytes < f.bytes else "stronger",
                    "download_gib": round(of.bytes / GiB, 1),
                    "memory_gib": round(oc.need.total / GiB, 1),
                    "fits": oc.fits and oc.disk_ok,
                    "fit_level": oc.fit_level,
                    "speed_class": oc.speed_class,
                    "installed": downloader.is_downloaded(m, of),
                }
            )
        # same family, other sizes
        for sib in cat.models:
            if sib.id == m.id or sib.family != m.family:
                continue
            best = fit_ids.get(sib.id)
            sf = sib.file(best.quant) if best else sib.smallest()
            sc = best or evaluate(sib, sf, budget, ctx)
            bigger = (sib.params_b or 0) > (m.params_b or 0) or sib.quality_tier > m.quality_tier
            versions.append(
                {
                    "kind": "size",
                    "model_id": sib.id,
                    "name": sib.name,
                    "quant": sf.quant,
                    "relation": "stronger" if bigger else "lighter",
                    "download_gib": round(sf.bytes / GiB, 1),
                    "memory_gib": round(sc.need.total / GiB, 1),
                    "fits": sc.fits and sc.disk_ok,
                    "fit_level": sc.fit_level,
                    "speed_class": sc.speed_class,
                    "installed": any(downloader.is_downloaded(sib, x) for x in sib.files),
                }
            )
        versions.sort(key=lambda v: (v["relation"] != "lighter", v["memory_gib"]))
        it["versions"] = versions
        # the best general AIs that fit, one step down and one step up, whatever the family
        generals = [x for x in rec.fits if x.role == "general" and x.model_id != m.id]
        up = [x for x in generals if x.quality_tier > m.quality_tier]
        down = [x for x in generals if x.quality_tier < m.quality_tier]
        it["alternatives"] = {
            "stronger": {
                "model_id": up[0].model_id,
                "name": up[0].name,
                "quant": up[0].quant,
                "download_gib": round(up[0].need.weights / GiB, 1),
                "speed_class": up[0].speed_class,
            }
            if up
            else None,
            "lighter": {
                "model_id": down[0].model_id,
                "name": down[0].name,
                "quant": down[0].quant,
                "download_gib": round(down[0].need.weights / GiB, 1),
                "speed_class": down[0].speed_class,
            }
            if down
            else None,
        }
        out.append(it)
    return out
