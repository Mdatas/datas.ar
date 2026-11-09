# Video — making and editing (plan and honest limits)

Everything here needs a real graphics card; the Run screen says so per device. Phones: none of it.

## 1. Making video from text or a picture — next, through the engine we already ship

stable-diffusion.cpp (the image engine) also runs video models: **Wan 2.1/2.2** (5 B and 14 B),
**LTX-2.3/2.5**, HunyuanVideo 1.5 (`docs/wan.md`, `docs/ltx2.md` upstream). Cost: a few seconds
of 480–720p video takes minutes on a 12 GB card and needs 12 GB+ of graphics memory with the
quantised 5 B model; the 14 B models want 24 GB. On a processor alone it is hours — the verdict is
"no" there. Same download/run pattern as images; a "Video" tab next to "Images".

## 2. Editing video

| Wish | How it is done with open tools | Needs | Datas plan |
|---|---|---|---|
| **Make someone speak another language** (dubbing) | hearing (whisper.cpp) → translation (the chat model) → the speaker's voice in the new language (voice cloning: Chatterbox / F5-TTS, open) → lip movement redone (lip-sync models such as LatentSync / MuseTalk, open) | 8 GB+ card; PyTorch-based models, so a bigger install than the ggml engines | **planned**: "Translate my video", only for people who agreed (see below) |
| **Replace a flat object — a wine label, a sign, a screen** | two ways: (a) classical, no AI: track the label's four corners with OpenCV and composite the new artwork — exact, works on the processor, best for rigid flat things; (b) generative: SAM 2 (Meta) tracks the region, a video inpainting model repaints it | (a) any computer; (b) 12–16 GB card | **planned**: (a) first — it is the reliable one for labels and bottles — then (b) |
| **Change what someone does** (video-to-video with instructions) | Wan 2.2 VACE / LTX video-to-video | 16 GB+ card; quality uneven | later, experimental |
| **Face swapping onto another person** | open tools exist (InsightFace-based swappers) | 6 GB+ card | **not in Datas** — see below |

## 3. The line Datas draws, and why

Dubbing your own videos, your products, your actors with their consent: yes, and Datas will
make it easy. Putting words in the mouth of someone who did not agree, or their face on another
body: no. That is the single most-used recipe for fraud and harassment, it is illegal in a growing
number of places (the EU AI Act requires deepfakes to be labelled; non-consensual intimate
deepfakes are criminal in many countries), and a tool for non-technical users must not make it a
one-click thing. So:

- **Consent gate**: the video-editing features that change a person ask the user to confirm the
  people in the video agreed, every time, in plain words.
- **Marked as AI-edited**: outputs carry an "edited with AI" note in the file's metadata (C2PA-style
  content credentials where the format allows) and an optional small visible mark.
- **No face swap of other people** ships in Datas. Users who want that have other tools; Datas
  will not be one.
- Label/object replacement and video generation from text have no such gate: no real person is
  changed.

## 4. Order of work

1. Video generation (Wan 2.2 5 B / LTX-2.3) — same engine, same pattern as images.
2. "Replace a label/object" classical tracker + compositor (CPU, deterministic).
3. "Translate my video": whisper.cpp → chat model → voice clone → lip-sync, with the consent gate
   and the AI-edited mark; PyTorch-based pieces downloaded on first use, GPU only.
4. Generative inpainting (SAM 2 + video inpainting) for non-flat objects.
