# Video — every way Datas offers to make and edit it

Datas is a neutral launcher: it checks the device, says what to expect, downloads, starts and
shows. It does not filter or alter what a model or tool does; each model and tool keeps its own
behaviour and licence, and what is made with them is the user's responsibility (see the licence
shown on every card). Nothing is hidden because it is demanding — the verdict says *yes*,
*yes, slowly* or *below what it needs*, and "Try anyway" is always there.

| I want to… | Where in Datas | What runs underneath | Needs (guidance) |
|---|---|---|---|
| Make a clip from a description | Images & video → Video clip | stable-diffusion.cpp + **Wan 2.2 TI2V 5B** (GGUF) | 8 GB+ card (12+ comfortable); hours on a processor |
| Animate a picture | same screen, "Start from this picture" | same | same |
| Longer / higher-quality video, other models (LTX-Video, HunyuanVideo, Wan 14B, CogVideoX…) | More tools → **ComfyUI** | ComfyUI templates | 12–24 GB card |
| Change what happens in a video (video→video), restyle | More tools → ComfyUI | Wan VACE / LTX video-to-video workflows | 16 GB+ card |
| Replace or repaint part of a video — a label, a bottle, a sign, a background | More tools → ComfyUI | masking/tracking + video inpainting workflows | 12 GB+ card |
| Put a face on another person (face swap), photos or video | More tools → **FaceFusion** | `face_swapper`, `deep_swapper` | works on a processor, faster with any card |
| Make lips follow a new audio track (dubbing into another language) | More tools → FaceFusion (`lip_syncer`); the new audio can come from Datas' own voice (Kokoro) or any audio file | lip-sync | same |
| Restore, sharpen, upscale, colourise, change age/expression, remove background | More tools → FaceFusion | `face_enhancer`, `frame_enhancer`, `frame_colorizer`, `age_modifier`, `expression_restorer`, `background_remover` | same |
| Transcribe / subtitle a video | chat → Talk, or `datas voice hear` | whisper.cpp | any computer |

## Built-in video engine

`datas/engines/images.py` runs video through the same `sd-server` as pictures
(`POST /sdcpp/v1/vid_gen`, result as WebM). Recipe in `datas/catalog/media.json`
(`video.recipes.wan2.2-ti2v-5b`): diffusion model GGUF Q3_K_S / Q4_K_M / Q8_0 chosen by memory,
umt5-xxl text encoder GGUF, Wan 2.2 VAE; defaults 832×480, 33 frames at 16 fps, 20 steps, CFG 6,
flow shift 3 (from upstream `docs/wan.md`). File sizes are the exact Hugging Face values.

## Not built yet

- A one-click "translate my video" chain (whisper → chat model → cloned voice → lip-sync). All
  pieces are reachable today, by hand, through the tools above.
- Voice cloning as a Datas engine (Kokoro has fixed voices).
- Video on phones.
