"""Integration: real llama.cpp binaries + a synthetic model.

Skipped automatically when the runtime is not installed (no network in CI). Run
`datas install` first to enable it locally.
"""

from pathlib import Path

import httpx
import pytest

from datas.config import Config
from datas.runtime import gguf_meta, llamacpp
from datas.runtime.process import LlamaServer
from tests.make_tiny_gguf import build


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    return build(tmp_path_factory.mktemp("m") / "tiny.gguf")


def test_gguf_header_roundtrip(tiny: Path):
    f = gguf_meta.read(tiny)
    assert f.architecture == "llama" and f.layers == 2 and f.kv_heads == 4 and f.head_dim == 16
    assert f.context_train == 512
    assert f.kv_hint().bytes_per_token(16) == 2 * 2 * 4 * 16 * 2


def test_server_roundtrip(tiny: Path):
    cfg = Config.load()
    if not llamacpp.installed_dir(cfg):
        pytest.skip("llama.cpp runtime not installed (run `datas install`)")
    srv = LlamaServer(cfg)
    args = [
        "-m",
        str(tiny),
        "--host",
        "127.0.0.1",
        "--port",
        "8499",
        "-c",
        "256",
        "-t",
        "2",
        "--jinja",
        "-ngl",
        "0",
        "--no-warmup",
    ]
    st = srv.start(args, str(tiny), "tiny", "F32", port=8499, timeout=120)
    try:
        assert st.pid and srv.running()
        r = httpx.post(
            "http://127.0.0.1:8499/v1/chat/completions",
            json={
                "model": "tiny",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 4,
            },
            timeout=60,
        )
        assert r.status_code == 200
        # random weights may emit EOS early; we only care that generation happened
        assert 1 <= r.json()["usage"]["completion_tokens"] <= 4
    finally:
        srv.stop()
    assert not srv.running()
