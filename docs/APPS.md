# More tools — third-party AI applications

Some jobs are done best by complete programs that already exist. Datas installs and opens them;
it does not wrap or change them. Code: `datas/apps/` (`apps.json` recipes, `runner.py`).

## How it works

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

## Bundled recipes

| Tool | For | Licence | Pinned |
|---|---|---|---|
| ComfyUI | making and editing images and video with every current open model | GPL-3.0 | v0.44.2 |
| FaceFusion | face swap, lip-sync, face/frame restoration and editing | OpenRAIL-AS | 3.9.2 |

## Adding your own

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

## Specialist chat models

Not tools but models: Home → "Specialist" offers Math (Qwen2.5-Math 7B), Legal texts (Saul 7B)
and Medical (MedGemma 1.5 4B, own licence terms) besides Programming. They are ordinary catalog
entries with a `role`; add more in `datas/catalog/models.json`.
