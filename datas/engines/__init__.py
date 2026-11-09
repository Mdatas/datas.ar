"""Engines Datas can drive, one per kind of media. The user never sees these names: the Run
screen only shows what the device can carry ("Voice & sound", "Images", "Video").

| media                       | engine                | how it runs                          |
|-----------------------------|-----------------------|--------------------------------------|
| text, understanding images  | llama.cpp             | ``llama-server`` subprocess (runtime/)|
| speech → text (hearing)     | whisper.cpp           | in-process via ``pywhispercpp``      |
| text → speech (speaking)    | Kokoro-82M            | in-process via ``kokoro-onnx``       |
| images / video (making)     | stable-diffusion.cpp  | ``sd-server`` subprocess (planned)   |

Each engine module exposes: ``available()`` (is the software there), ``installed()`` (are the
model files there), an ``ensure_*`` download step that takes a Job, and the operation itself.
"""

from __future__ import annotations

ENGINES: list[dict] = [
    {
        "id": "llama.cpp",
        "media": ["text", "vision"],
        "name": "llama.cpp",
        "by": "ggml-org",
        "license": "MIT",
        "url": "https://github.com/ggml-org/llama.cpp",
    },
    {
        "id": "whisper.cpp",
        "media": ["speech-to-text"],
        "name": "whisper.cpp (via pywhispercpp)",
        "by": "ggml-org; bindings by absadiki",
        "license": "MIT",
        "url": "https://github.com/ggml-org/whisper.cpp",
    },
    {
        "id": "kokoro",
        "media": ["text-to-speech"],
        "name": "Kokoro-82M (via kokoro-onnx + ONNX Runtime)",
        "by": "hexgrad; bindings by thewh1teagle",
        "license": "Apache-2.0 (model), MIT (bindings)",
        "url": "https://huggingface.co/hexgrad/Kokoro-82M",
    },
    {
        "id": "stable-diffusion.cpp",
        "media": ["image", "video"],
        "name": "stable-diffusion.cpp",
        "by": "leejet",
        "license": "MIT",
        "url": "https://github.com/leejet/stable-diffusion.cpp",
        "status": "planned",
    },
]
