"""The Datas guide: a chat skill that knows *this* device, the catalog and how to use AI well.

Everything it knows is assembled here from live data (device scan, abilities verdicts, installed
and recommended models, voice/agent status) plus a short, static primer on prompting. It runs on
whatever AI is currently running — no extra download — so it exists from the first run onwards.
"""

from __future__ import annotations

from datas.catalog.compare import comparable
from datas.config import home
from datas.recommend.abilities import assess

GiB = 2**30

PRIMER_EN = """How to get good results from a local AI (keep these in mind when advising):
- Say what you want, for whom, and in what shape (length, format, language). One task at a time.
- Give the material: paste the text, the data, the example to imitate. Small local models guess badly from hints.
- Ask for a draft, then refine in follow-ups ("shorter", "more formal", "add a table"). Iteration beats one perfect prompt.
- The AI only knows what is in the conversation plus its training; it has no internet unless the user switches it on for the session, and no memory between chats in Forget mode.
- Context = how much text the AI keeps in mind at once (shown as "memory" in the recommendation). Long documents must be split or added as Documents.
- Specialised models (coding) beat general ones at their job and are worse at everything else.
- Pictures: only models marked "understands pictures" can look at images; none here can draw yet.
- Facts, numbers, names and dates: always double-check; smaller models invent confidently.
- Speed is bounded by the device: a "slow" verdict means it works but you wait; closing other heavy programs helps.
- Voice: the Talk button hears you (whisper.cpp), "Read answers aloud" speaks (Kokoro). Nothing is recorded to disk.
- The agent (separate window) does file, document and web tasks in the folders the user ticks, asks before risky actions, and can run on a schedule. It cannot click around other programs yet.
"""

RULES_EN = """You are the Datas guide. Answer questions about THIS device, what it can and cannot do with AI, which of the available models fits which task, and how to use them well. Rules:
- Use only the facts below. Never invent a model, a number or a capability. If the facts do not cover it, say so and point to About → sources, or suggest the user run the device check again.
- Be plain and short. Spell out every acronym the first time (RAM = working memory, GPU = graphics card, VRAM = graphics memory, LLM = large language model). Assume the user has never used AI tools.
- When the user asks "can my computer do X", answer with the verdict below and what it would need.
- When they ask which AI to use, pick from the installed or recommended list and say why in one or two sentences.
- You cannot change settings or start models yourself; tell the user where to click (Home → Run; My AIs; Settings; the agent window).
"""


def _gpu_line(spec) -> str:  # noqa: ANN001
    if not spec.gpus:
        return "no dedicated graphics card (CPU only)"
    parts = []
    for g in spec.gpus:
        v = f" {g.vram_total / GiB:.0f} GB graphics memory" if g.vram_total else ""
        parts.append(f"{g.name}{v}{' (shared memory)' if g.unified else ''}")
    return ", ".join(parts)


def build(core, lang: str = "en") -> str:  # noqa: ANN001 - Datas orchestrator
    spec = core.spec()
    rec = core.recommendation()
    va = core.voice_status()
    abilities = assess(spec, rec, voice_available=va["available"]["stt"] and va["available"]["tts"])
    lines = [RULES_EN, "FACTS ABOUT THIS DEVICE"]
    lines.append(
        f"- {spec.os} · {spec.cpu_name} ({spec.cpu_cores_logical} threads) · {spec.ram_total / GiB:.0f} GB RAM · "
        f"{_gpu_line(spec)} · {spec.disk_free_models / GiB:.0f} GB free for models · form: {spec.form_factor}"
    )
    lines.append(
        f"- The AI may use up to {rec.budget.total_budget / GiB:.1f} GB; {rec.budget.ram_headroom / GiB:.0f} GB are kept free for the rest of the computer (resource mode: {core.cfg.resource_mode})."
    )
    lines.append("\nWHAT THIS DEVICE CAN DO (verdicts from the device check)")
    for a in abilities:
        why = a.why_es if lang == "es" else a.why
        needs = a.needs_es if lang == "es" else a.needs
        lines.append(
            f"- {a.id}: {a.verdict.upper()} — {why}" + (f" Needs: {needs}" if needs else "")
        )

    lines.append("\nINSTALLED AIs (ready to start from My AIs)")
    from datas import library

    inst = library.installed()
    if inst:
        for m in inst:
            lines.append(
                f"- {m['name']} ({m.get('quant', '')}, {m.get('size_gib', '?')} GB): good for {', '.join(m.get('use_cases') or [])}; "
                f"can {', '.join(m.get('capabilities') or [])}. Limits: {m.get('limits') or '-'}"
            )
    else:
        lines.append("- none yet")
    st = core.server.state
    lines.append(f"- Currently running: {st.model_id or 'nothing'}")

    lines.append("\nRECOMMENDED FOR THIS DEVICE (from the last check)")
    shown = ([rec.default] if rec.default else []) + [c for c in rec.fits if c is not rec.default][
        :5
    ]
    for c in shown:
        cmp = comparable(c.quality_tier)
        p = c.plain()
        lines.append(
            f"- {c.name} ({c.quant}; {p['download']}, {p['memory']}): speed {c.speed_class}, fit {c.fit_level}, "
            f"capabilities {', '.join(c.capabilities)}; roughly comparable to {cmp['openai']} / {cmp['google']} / {cmp['anthropic']}. "
            f"Limits: {p['limits']}"
        )
    if rec.does_not_fit:
        lines.append(
            "- Does NOT fit here: "
            + "; ".join(
                f"{c.name} (needs {c.need.total / GiB:.1f} GB)" for c in rec.does_not_fit[:6]
            )
        )

    # the full catalog only when the running context can afford it (~1k tokens)
    lines.append("\nALL MODELS DATAS KNOWS (name — size — good for — limits — license)")
    models = core.catalog.models if (core.cfg.context or 8192) >= 6144 else []
    if not models:
        lines.append(
            "- (list shortened: the current AI keeps little text in mind; see Home → other recommendations)"
        )
    for m in models:
        size = f"{m.params_b:g}B params" if m.params_b else "size unknown"
        lines.append(
            f"- {m.name} — {size} — {', '.join(m.use_cases or [])} — {m.limits or '-'} — {m.license}"
        )

    v_inst = va["installed"]
    lines.append("\nVOICE")
    lines.append(
        f"- packages available: {va['available']['stt'] and va['available']['tts']}; installed: hearing {v_inst['stt_models'] or 'none'}, speaking {'yes' if v_inst['tts'] else 'no'}; microphone found: {va['available']['mic']}"
    )
    lines.append("\nPRIVACY")
    lines.append(
        f"- mode: {core.cfg.memory_mode} ({'conversations and notes are kept on this computer' if not core.cfg.forget else 'nothing is saved, no logs'}); internet per session: {'on by default' if core.cfg.internet_default else 'off by default'}; data folder: {home()}"
    )
    lines.append("\n" + PRIMER_EN)
    if lang == "es":
        lines.append("Answer in Spanish (Argentina) unless the user writes in another language.")
    return "\n".join(lines)


STARTERS = {
    "en": [
        "What can my computer do with AI, and what can't it do?",
        "Which of my AIs should I use to write emails? And for summaries?",
        "How do I ask so the answers get better?",
        "Why is this model recommended and not a bigger one?",
        "What does 'context' mean and why does it matter?",
        "How do I make the AI forget everything about me?",
    ],
    "es": [
        "¿Qué puede hacer mi computadora con IA y qué no?",
        "¿Cuál de mis IAs uso para escribir emails? ¿Y para resumir?",
        "¿Cómo pregunto para que las respuestas sean mejores?",
        "¿Por qué me recomiendan este modelo y no uno más grande?",
        "¿Qué es el 'contexto' y por qué importa?",
        "¿Cómo hago para que la IA olvide todo sobre mí?",
    ],
}


def offline_answer(core, question: str, lang: str = "en") -> str:  # noqa: ANN001
    """Answer without any AI: pick the facts that match the question. Used before the first
    model is installed and while it downloads, so the guide exists from the first second."""
    es = lang == "es"
    q = question.lower()
    spec = core.spec()
    rec = core.recommendation()
    va = core.voice_status()
    abil = assess(spec, rec, voice_available=va["available"]["stt"] and va["available"]["tts"])
    names = {
        "text": ("Chat & writing", "Chat y escritura"),
        "images": ("Understanding pictures", "Entender imágenes"),
        "coding": ("Programming", "Programar"),
        "agents": ("Tasks for me (agent)", "Tareas por mí (agente)"),
        "sound": ("Voice", "Voz"),
        "image_gen": ("Making images", "Crear imágenes"),
        "video": ("Making video", "Crear video"),
        "pool": ("Devices together", "Dispositivos en conjunto"),
    }
    word = {
        "yes": ("yes", "sí"),
        "slow": ("yes, slowly", "sí, lento"),
        "no": ("no", "no"),
        "not_yet": ("not yet in Datas", "todavía no en Datas"),
    }

    def verdicts() -> str:
        rows = []
        for a in abil:
            n = names.get(a.id, (a.id, a.id))[es]
            needs = a.needs_es if es else a.needs
            rows.append(
                f"• {n}: {word[a.verdict][es]} — {a.why_es if es else a.why}"
                + (f" ({'Necesita' if es else 'Needs'}: {needs})" if needs else "")
            )
        return "\n".join(rows)

    def device() -> str:
        return (
            f"{spec.cpu_name}, {spec.ram_total / GiB:.0f} GB RAM ({'memoria de trabajo' if es else 'working memory'}), {_gpu_line(spec)}, "
            f"{spec.disk_free_models / GiB:.0f} GB {'libres en disco' if es else 'free on disk'}."
        )

    def reco() -> str:
        if not rec.default:
            return (
                "Ningún modelo de chat entra con los ajustes actuales."
                if es
                else "No chat model fits with the current settings."
            )
        c = rec.default
        p = c.plain("es" if es else "en")
        cmp = comparable(c.quality_tier, "es" if es else "en")
        others = ", ".join(x.name for x in rec.fits if x is not c)[:300]
        return (
            (
                f"Recomendado: {c.name} — {p['download']} {p['memory']} Parecido a: {cmp['openai']} / {cmp['google']} / {cmp['anthropic']}. Límites: {p['limits']}"
                + (f"\nTambién entran: {others}." if others else "")
            )
            if es
            else (
                f"Recommended: {c.name} — {p['download']} {p['memory']} Roughly like: {cmp['openai']} / {cmp['google']} / {cmp['anthropic']}. Limits: {p['limits']}"
                + (f"\nAlso fit: {others}." if others else "")
            )
        )

    tips = (
        "Para mejores respuestas: decí qué querés, para quién y en qué formato; pegá el texto o los datos; pedí un borrador y después ajustá ('más corto', 'más formal'); una tarea por vez; verificá cifras, nombres y fechas."
        if es
        else "For better answers: say what you want, for whom and in what shape; paste the text or data; ask for a draft, then refine ('shorter', 'more formal'); one task at a time; double-check numbers, names and dates."
    )
    ctx = (
        "El 'contexto' es cuánto texto la IA tiene presente a la vez. Si el documento es más largo, hay que partirlo o agregarlo en 'Mis documentos'."
        if es
        else "'Context' is how much text the AI keeps in mind at once. Longer documents must be split, or added under 'My documents'."
    )
    forget = (
        "Ajustes → Privacidad → 'Olvidar todo': no se guarda nada. 'Borrar todo lo que recuerda' elimina lo ya guardado."
        if es
        else "Settings → Privacy → 'Forget everything': nothing is saved. 'Delete everything it remembers' removes what was stored."
    )
    parts: list[str] = []
    if any(k in q for k in ("prompt", "ask", "pregunt", "mejor", "better")):
        parts.append(tips)
    if any(k in q for k in ("context", "contexto")):
        parts.append(ctx)
    if any(k in q for k in ("forget", "olvid", "privac", "borr")):
        parts.append(forget)
    if any(
        k in q
        for k in (
            "which",
            "cuál",
            "cual",
            "recom",
            "model",
            "bigger",
            "grande",
            "email",
            "resum",
            "summar",
        )
    ):
        parts.append(reco())
    if not parts or any(
        k in q
        for k in (
            "can",
            "puede",
            "computer",
            "computadora",
            "device",
            "equipo",
            "video",
            "imag",
            "voz",
            "voice",
        )
    ):
        parts = [("Tu equipo: " if es else "Your device: ") + device(), verdicts()] + parts
    note = (
        "(Respuesta armada con los datos de tu equipo, sin IA todavía. Cuando haya una IA corriendo, la guía conversa de verdad.)"
        if es
        else "(Answer assembled from your device's facts, no AI yet. Once an AI is running, the guide really converses.)"
    )
    return "\n\n".join(parts + [note])
