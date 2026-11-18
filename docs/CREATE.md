# Making pictures and video, and bigger creative tools

Everything Datas offers for making things other than text: its own picture and video
engine, and complete third-party programs it installs and opens for you.

## Video — every way Datas offers to make and edit it

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

### Built-in video engine

`datas/engines/images.py` runs video through the same `sd-server` as pictures
(`POST /sdcpp/v1/vid_gen`, result as WebM). Recipe in `datas/catalog/media.json`
(`video.recipes.wan2.2-ti2v-5b`): diffusion model GGUF Q3_K_S / Q4_K_M / Q8_0 chosen by memory,
umt5-xxl text encoder GGUF, Wan 2.2 VAE; defaults 832×480, 33 frames at 16 fps, 20 steps, CFG 6,
flow shift 3 (from upstream `docs/wan.md`). File sizes are the exact Hugging Face values.

### Not built yet

- A one-click "translate my video" chain (whisper → chat model → cloned voice → lip-sync). All
  pieces are reachable today, by hand, through the tools above.
- Voice cloning as a Datas engine (Kokoro has fixed voices).
- Video on phones.

## More tools — third-party AI applications

Some jobs are done best by complete programs that already exist. Datas installs and opens them;
it does not wrap or change them. Code: `datas/apps/` (`apps.json` recipes, `runner.py`).

### How it works

1. **uv** (astral-sh, pinned release) is downloaded once into `<data>/tools/`. It provides Python
   itself and isolated environments, so nothing needs to be installed on the computer first.
2. The program's source is downloaded from its GitHub repository **at a pinned tag** into
   `<data>/apps/<id>/src`, an environment is created in `<data>/apps/<id>/venv`, and the recipe's
   install steps run (packages are chosen for the device: NVIDIA, AMD on Linux, Mac, or processor).
3. The program is started on a local port (127.0.0.1 only) and shown in its own Datas window.
4. Stop, Remove (everything it downloaded) — from the same card. Logs: `<data>/logs/app-<id>.log`
   (off in Forget mode).

Each card shows the maker, licence, website, what it is for in plain words, and a verdict for
this device (guidance only; "Install and open" always works).

### Bundled recipes

| Tool | For | Licence | Pinned |
|---|---|---|---|
| ComfyUI | making and editing images and video with every current open model | GPL-3.0 | v0.44.2 |
| FaceFusion | face swap, lip-sync, face/frame restoration and editing | OpenRAIL-AS | 3.9.2 |

### Adding your own

Drop a JSON file into `<data>/apps.d/` with the same fields as an entry of `apps.json`:

```json
{"id": "mytool", "name": "My tool", "maker": "…", "license": "…", "url": "https://…",
 "tasks": ["image"], "plain_en": "…", "plain_es": "…",
 "source": {"repo": "owner/repo", "tag": "v1.2.3"}, "python": "3.12",
 "install": [{"pip_requirements": "requirements.txt"}],
 "launch": {"args": ["app.py", "--port", "{port}"], "env": {"GRADIO_SERVER_PORT": "{port}"}},
 "port": 7861, "needs_ffmpeg": false, "guide": {"gpu": true, "vram_gib": 8, "ram_gib": 16}}
```

Install step kinds: `{"pip": [...], "extra_by_accel": {...}}`, `{"pip_requirements": "file"}`,
`{"python": ["script.py", "{var}"], "vars_by_accel": {...}}`. Accelerator keys, most specific
first: `mac`, `nvidia`, `amd-linux`, `windows-gpu`, `cpu`.

### Specialist chat models

Not tools but AIs: *Add an AI* lists Math (Qwen2.5-Math 7B), Legal texts (Saul 7B) and
Medical (MedGemma 1.5 4B, own licence terms) among the other AIs, each with its verdict for
this device; a specialist is never picked unless you choose it. They are ordinary catalog
entries with a `role`; add more in `datas/catalog/models.json`.
