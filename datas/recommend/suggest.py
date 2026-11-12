""" "Try this AI instead": a faster one when answers are slow or memory runs short, and one that
can do what the current AI cannot (see pictures, use tools, reason, write code) — always one
that fits this device, an AI already here first. When none can, it says so plainly.
"""

from __future__ import annotations

from datas.recommend.engine import Candidate, Recommendation

NEEDS = {
    "vision": "see pictures",
    "tools": "use tools (the agent, internet in a chat)",
    "reasoning": "think step by step",
    "coding": "write code",
}

_SPEED = {"fast": 0, "ok": 1, "slow": 2, "crawl": 3}


def _pick(cands: list[Candidate], installed: set[str]) -> Candidate | None:
    if not cands:
        return None
    # an AI already on the device first (no download), then the best of the rest
    here = [c for c in cands if c.model_id in installed]
    return (here or cands)[0]


def faster(rec: Recommendation, current_id: str, current_bytes: int, installed: set[str]) -> dict:
    """A smaller AI that fits and answers sooner: at most 60 % of the current file's size."""
    smaller = [
        c for c in rec.fits if c.need.weights <= 0.6 * current_bytes and c.model_id != current_id
    ]
    smaller.sort(key=lambda c: (_SPEED.get(c.speed_class, 3), -c.effective_tier, c.need.weights))
    c = _pick(smaller, installed)
    if not c:
        return {"none": "This is already the smallest AI that suits this device."}
    return _out(c, installed)


def able(rec: Recommendation, need: str, installed: set[str]) -> dict:
    """The best AI that can do ``need`` and fits this device (rec was made with want=[need])."""
    c = rec.default or _pick(rec.fits, installed)
    if c and c.model_id not in installed:
        here = [x for x in rec.fits if x.model_id in installed]
        if here and here[0].effective_tier >= c.effective_tier - 1:
            c = here[0]  # nearly as good and already here
    if not c:
        smallest = min(rec.does_not_fit, key=lambda x: x.need.total, default=None)
        return {
            "none": f"No AI that can {NEEDS.get(need, need)} fits this device.",
            "smallest_gib": round(smallest.need.total / 2**30, 1) if smallest else None,
            "smallest_name": smallest.name if smallest else None,
        }
    return _out(c, installed)


def _out(c: Candidate, installed: set[str]) -> dict:
    return {
        "model_id": c.model_id,
        "name": c.name,
        "quant": c.quant,
        "installed": c.model_id in installed,
        "gib": round(c.need.weights / 2**30, 1),
        "speed": c.speed_class,
    }
