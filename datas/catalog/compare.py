"""Plain-language context for non-technical users: which paid AI is this open model like?

These are *rough class equivalents* chosen by the curator — "feels about as capable as" —
not benchmark results. Paid frontier models (GPT-5.5, Gemini 3.1 Pro, Claude Opus 5.5)
stay clearly ahead of anything that fits on a home computer in 2026; the point is to give
someone who has only used ChatGPT a familiar yardstick. Names checked Nov 2026.
"""

from __future__ import annotations

DISCLAIMER = (
    "Rough comparison by capability class, chosen by the Datas team — not a benchmark. "
    "The paid models also have internet search, bigger memories and the latest news built in."
)

# tier → (OpenAI, Google, Anthropic, one-line verdict)
TIERS: dict[int, dict[str, str]] = {
    1: {
        "openai": "below GPT-5.4 Nano",
        "google": "below Gemini 3.5 Flash-Lite",
        "anthropic": "below Claude Haiku 5.5",
        "verdict": "Much simpler than any paid AI — good for quick, short help on a very small device.",
    },
    2: {
        "openai": "approaching GPT-5.4 Nano",
        "google": "approaching Gemini 3.5 Flash-Lite",
        "anthropic": "approaching Claude Haiku 5.5",
        "verdict": "Handles everyday questions and short texts; the paid entry-level models are still noticeably better.",
    },
    3: {
        "openai": "GPT-5.4 Nano class",
        "google": "Gemini 3.5 Flash-Lite class",
        "anthropic": "Claude Haiku 5.5 class",
        "verdict": "About the level of the cheapest paid tiers: good everyday assistant, verify facts.",
    },
    4: {
        "openai": "GPT-5.4 Mini class",
        "google": "Gemini 3.5 Flash class",
        "anthropic": "between Claude Haiku 5.5 and Sonnet 5.5",
        "verdict": "Comparable to the mid-tier paid models most people actually use day to day.",
    },
    5: {
        "openai": "GPT-5.4 Mini to GPT-5.4 class",
        "google": "Gemini 3.5 Flash class",
        "anthropic": "Claude Sonnet 5.5 class",
        "verdict": "Close to the mainstream paid models; the flagship paid models (GPT-5.5, Gemini 3.1 Pro, Claude Opus 5.5) remain stronger.",
    },
}


def comparable(tier: int, lang: str = "en") -> dict[str, str]:
    """The comparison for a quality tier, said in ``lang`` (Spanish lives in datas/words.py)."""
    from datas.words import tr

    t = TIERS.get(max(1, min(5, tier)), TIERS[3])
    return {k: tr(v, lang) for k, v in dict(t, disclaimer=DISCLAIMER).items()}
