"""What this device can do — a verdict per ability, in plain words.

The Run screen never greys an option out beforehand; it asks the device. For each ability we
return one of:

* ``yes``     — works comfortably here
* ``slow``    — works, but noticeably slow (the user decides)
* ``no``      — this device cannot do it; ``needs`` says what would be required
* ``not_yet`` — the device could do it, but Datas has not wired that engine yet (honest gap)

Rules are conservative engineering thresholds, not measurements; they live in one place so
they are easy to tune as benchmarks come in (``datas bench``). Memory figures: the text model
comes from the real recommender (exact GGUF sizes + KV cache); voice from ``media.json``;
image/video making from the public requirements of stable-diffusion.cpp model families
(Z-Image/Qwen-Image ≈ 6–8 B params, Wan 2.2 ≈ 5 B + VAE at 480p).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from datas.hardware.detect import DeviceSpec
from datas.recommend.engine import Recommendation

GiB = 2**30


@dataclass
class Ability:
    id: str
    verdict: str  # yes | slow | no | not_yet
    why: str
    why_es: str
    needs: str = ""
    needs_es: str = ""
    engine: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "verdict": self.verdict,
            "why": self.why,
            "why_es": self.why_es,
            "needs": self.needs,
            "needs_es": self.needs_es,
            "engine": self.engine,
            **self.extra,
        }


def _gpu_vram_gib(spec: DeviceSpec) -> float:
    return spec.dedicated_vram_total / GiB


def _unified_gib(spec: DeviceSpec) -> float:
    return spec.ram_total / GiB if any(g.unified for g in spec.gpus) else 0.0


def assess(spec: DeviceSpec, rec: Recommendation, voice_available: bool = True) -> list[Ability]:
    out: list[Ability] = []
    fits = rec.fits
    best = rec.default
    vram = _gpu_vram_gib(spec)
    uni = _unified_gib(spec)
    ram = spec.ram_total / GiB
    cores = spec.cpu_cores_logical or 1
    phone = spec.form_factor == "phone"

    # ---- text --------------------------------------------------------------
    if best:
        slow = best.speed_class in ("slow", "crawl")
        out.append(
            Ability(
                "text",
                "slow" if slow else "yes",
                f"{best.name} fits with {rec.budget.ram_headroom / GiB:.0f} GB kept free; "
                + (
                    "it will answer slowly on this processor."
                    if slow
                    else "answers at a comfortable pace."
                ),
                f"{best.name} entra dejando {rec.budget.ram_headroom / GiB:.0f} GB libres; "
                + (
                    "va a responder lento en este procesador." if slow else "responde a buen ritmo."
                ),
                engine="llama.cpp",
            )
        )
    else:
        out.append(
            Ability(
                "text",
                "no",
                "No chat model fits in the memory this device can spare.",
                "Ningún modelo de chat entra en la memoria que este equipo puede ceder.",
                needs="about 3 GB of free working memory (RAM) for the smallest useful AI",
                needs_es="unos 3 GB de memoria de trabajo (RAM) libre para la IA útil más chica",
                engine="llama.cpp",
            )
        )

    # ---- understanding pictures (vision) -----------------------------------
    vis = [c for c in fits if "vision" in c.capabilities]
    if vis:
        c = vis[0]
        out.append(
            Ability(
                "images",
                "slow" if c.speed_class in ("slow", "crawl") else "yes",
                f"{c.name} can look at photos, screenshots and documents.",
                f"{c.name} puede mirar fotos, capturas y documentos.",
                engine="llama.cpp",
            )
        )
    else:
        out.append(
            Ability(
                "images",
                "no",
                "The models that understand pictures need more memory than this device can spare.",
                "Los modelos que entienden imágenes necesitan más memoria de la que este equipo puede ceder.",
                needs="about 5 GB free for the smallest picture-capable AI",
                needs_es="unos 5 GB libres para la IA más chica que entiende imágenes",
                engine="llama.cpp",
            )
        )

    # ---- coding ------------------------------------------------------------
    cod = [c for c in fits if "coding" in c.capabilities or c.role == "coding"]
    if cod:
        c = cod[0]
        out.append(
            Ability(
                "coding",
                "slow" if c.speed_class in ("slow", "crawl") else "yes",
                f"{c.name} writes and fixes code here.",
                f"{c.name} escribe y corrige código acá.",
                engine="llama.cpp",
            )
        )
    else:
        out.append(
            Ability(
                "coding",
                "no",
                "No coding-capable model fits.",
                "No entra ningún modelo que programe bien.",
                needs="about 6 GB free",
                needs_es="unos 6 GB libres",
                engine="llama.cpp",
            )
        )

    # ---- agents (tools + enough context) ------------------------------------
    ag = [c for c in fits if "tools" in c.capabilities]
    if ag and rec.context >= 8192:
        c = ag[0]
        slow = c.speed_class in ("slow", "crawl")
        out.append(
            Ability(
                "agents",
                "slow" if slow else "yes",
                f"{c.name} can use tools (files, web, commands) step by step"
                + ("; each step will take a while on this processor." if slow else "."),
                f"{c.name} puede usar herramientas (archivos, web, comandos) paso a paso"
                + ("; cada paso va a tardar en este procesador." if slow else "."),
                engine="llama.cpp",
            )
        )
    elif ag:
        out.append(
            Ability(
                "agents",
                "slow",
                "A tool-capable model fits, but only with a short memory (context); multi-step tasks may lose track.",
                "Entra un modelo con herramientas, pero con memoria corta (contexto); las tareas largas pueden perder el hilo.",
                needs="about 2 GB more free memory for an 8k-word context",
                needs_es="unos 2 GB más libres para un contexto de 8 mil palabras",
                engine="llama.cpp",
            )
        )
    else:
        out.append(
            Ability(
                "agents",
                "no",
                "No model that can use tools fits.",
                "No entra ningún modelo que use herramientas.",
                needs="about 5 GB free",
                needs_es="unos 5 GB libres",
                engine="llama.cpp",
            )
        )

    # ---- voice: hearing + speaking (CPU) ------------------------------------
    if phone:
        out.append(
            Ability(
                "sound",
                "not_yet",
                "This phone could run the small hearing model, but the phone app does not include voice yet.",
                "Este teléfono podría correr el modelo de oído chico, pero la app del teléfono todavía no trae voz.",
                engine="whisper.cpp + Kokoro",
            )
        )
    elif not voice_available:
        out.append(
            Ability(
                "sound",
                "not_yet",
                "This copy of Datas was built without the voice packages; reinstall with the newest installer.",
                "Esta copia de Datas se armó sin los paquetes de voz; reinstalá con el instalador más nuevo.",
                engine="whisper.cpp + Kokoro",
            )
        )
    elif ram < 2:
        out.append(
            Ability(
                "sound",
                "no",
                "Less than 2 GB of memory: not enough for hearing and speaking next to a chat model.",
                "Menos de 2 GB de memoria: no alcanza para oír y hablar junto a un modelo de chat.",
                needs="2 GB of RAM",
                needs_es="2 GB de RAM",
                engine="whisper.cpp + Kokoro",
            )
        )
    else:
        slow = cores < 4
        out.append(
            Ability(
                "sound",
                "slow" if slow else "yes",
                "Hearing (whisper.cpp) and speaking (Kokoro) run on the processor"
                + (
                    "; with few cores, understanding a sentence takes a few seconds."
                    if slow
                    else "."
                ),
                "Oír (whisper.cpp) y hablar (Kokoro) corren en el procesador"
                + ("; con pocos núcleos, entender una frase tarda unos segundos." if slow else "."),
                engine="whisper.cpp + Kokoro",
            )
        )

    # ---- making images (stable-diffusion.cpp, Z-Image-Turbo) ----------------
    from datas.engines import images as image_engine

    ch = image_engine.choose(spec)
    if not ch.fits:
        out.append(
            Ability(
                "image_gen",
                "no",
                f"Making images needs about {ch.need_gib:.0f} GB of memory for the picture model; "
                "this device cannot spare it.",
                f"Crear imágenes necesita unos {ch.need_gib:.0f} GB de memoria para el modelo de imagen; "
                "este equipo no los puede ceder.",
                needs="a graphics card with 4 GB+ and 8 GB of RAM, or 12 GB+ of RAM for slow CPU use",
                needs_es="una placa de video de 4 GB+ y 8 GB de RAM, o 12 GB+ de RAM para uso lento en CPU",
                engine="stable-diffusion.cpp",
            )
        )
    else:
        slow = ch.speed in ("slow", "crawl")
        where = {
            "gpu": ("on the graphics card", "en la placa de video"),
            "unified": ("on the shared-memory chip", "en el chip de memoria compartida"),
            "cpu": ("on the processor alone", "solo con el procesador"),
        }[ch.device]
        extra_en = (
            " Expect minutes per picture."
            if ch.speed == "crawl"
            else (" A picture takes a while." if slow else "")
        )
        extra_es = (
            " Contá minutos por imagen."
            if ch.speed == "crawl"
            else (" Cada imagen tarda un rato." if slow else "")
        )
        out.append(
            Ability(
                "image_gen",
                "slow" if slow else "yes",
                f"Z-Image-Turbo ({ch.total_bytes / GiB:.1f} GB download) makes 1024-px pictures {where[0]}.{extra_en}",
                f"Z-Image-Turbo ({ch.total_bytes / GiB:.1f} GB de descarga) crea imágenes de 1024 px {where[1]}.{extra_es}",
                engine="stable-diffusion.cpp",
                extra={"download_bytes": ch.total_bytes, "quant": ch.diffusion["quant"]},
            )
        )

    # ---- making video --------------------------------------------------------
    if vram >= 12 or uni >= 32:
        vid = (
            "not_yet",
            "This device has the graphics memory for short video clips; the engine comes after images.",
            "Este equipo tiene la memoria de video para clips cortos; el motor llega después de imágenes.",
        )
        needs = ("", "")
    elif vram >= 8:
        vid = (
            "not_yet",
            "Borderline: short low-resolution clips only, slowly; the engine comes after images.",
            "Al límite: solo clips cortos en baja resolución, lento; el motor llega después de imágenes.",
        )
        needs = (
            "12 GB+ of graphics memory for comfortable use",
            "12 GB+ de memoria de video para usarlo cómodo",
        )
    else:
        vid = (
            "no",
            "Making video needs a graphics card with 12 GB+ of memory; this device does not have it.",
            "Crear video necesita una placa de video con 12 GB+ de memoria; este equipo no la tiene.",
        )
        needs = ("graphics card with 12 GB+ of memory", "placa de video con 12 GB+ de memoria")
    out.append(
        Ability("video", vid[0], vid[1], vid[2], needs[0], needs[1], engine="stable-diffusion.cpp")
    )

    # ---- pooling ---------------------------------------------------------------
    if rec.budget.nodes > 1:
        out.append(
            Ability(
                "pool",
                "yes",
                f"{rec.budget.nodes} of your devices are working together ({rec.budget.total_budget / GiB:.0f} GB in total).",
                f"{rec.budget.nodes} de tus dispositivos trabajan juntos ({rec.budget.total_budget / GiB:.0f} GB en total).",
                engine="llama.cpp RPC",
            )
        )
    return out
