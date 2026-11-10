"""Third-party apps runner (with a fake recipe, no downloads), video recipe choice, starter AI
constants and the no-AI guide."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from datas.apps import runner
from datas.apps.runner import AppManager, accel_keys, load_recipes, uv_asset
from datas.config import Config
from datas.engines import images
from datas.hardware.detect import GPU
from tests.conftest import spec

G = 2**30


def test_bundled_recipes_are_complete():
    apps = {a["id"]: a for a in load_recipes()}
    assert {"comfyui", "facefusion"} <= set(apps)
    for a in apps.values():
        for k in (
            "name",
            "maker",
            "license",
            "url",
            "tasks",
            "plain_en",
            "plain_es",
            "source",
            "install",
            "launch",
            "port",
        ):
            assert a.get(k), (a["id"], k)
        assert a["source"]["repo"].count("/") == 1 and a["source"]["tag"]
    assert "face-swap" in apps["facefusion"]["tasks"] and "video-edit" in apps["comfyui"]["tasks"]


def test_uv_asset_and_accel_keys():
    assert uv_asset(spec(os_="windows")) == "uv-x86_64-pc-windows-msvc.zip"
    assert uv_asset(spec(os_="darwin", arch="arm64")) == "uv-aarch64-apple-darwin.tar.gz"
    assert uv_asset(spec(os_="linux")) == "uv-x86_64-unknown-linux-gnu.tar.gz"
    nv = GPU("nvidia", "x", 8 * G, 7 * G, False, "cuda")
    assert accel_keys(spec(os_="windows", gpus=[nv]))[:2] == ["nvidia", "windows-gpu"]
    assert accel_keys(spec(os_="linux", gpus=[])) == ["cpu"]
    assert (
        accel_keys(spec(os_="darwin", gpus=[GPU("apple", "M3", None, None, True, "metal")]))[0]
        == "mac"
    )


def test_runner_starts_and_stops_a_user_recipe(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    (tmp_path / "apps.d").mkdir()
    recipe = {
        "id": "hello",
        "name": "Hello",
        "maker": "test",
        "license": "MIT",
        "url": "https://example.org",
        "tasks": ["image"],
        "plain_en": "x",
        "plain_es": "x",
        "source": {"repo": "a/b", "tag": "1"},
        "install": [],
        "launch": {"args": ["-m", "http.server", "{port}", "--bind", "127.0.0.1"]},
        "port": 8765,
    }
    (tmp_path / "apps.d" / "hello.json").write_text(json.dumps(recipe))
    s = spec(ram=16, gpus=[])
    m = AppManager(Config(), lambda: s)
    assert any(a["id"] == "hello" and a["user_recipe"] for a in m.list())
    # pretend it is installed: the "venv python" is this interpreter
    d = m.dir("hello")
    (d / "src").mkdir(parents=True)
    (d / ".datas-installed").write_text("1")
    monkeypatch.setattr(AppManager, "py", lambda self, app_id: Path(sys.executable))
    r = m.start("hello", timeout=30)
    assert r["url"] == "http://127.0.0.1:8765/" and m.running("hello")
    assert any(a["id"] == "hello" and a["running"] for a in m.list())
    m.stop("hello")
    assert not m.running("hello")
    assert m.remove("hello") and not d.exists()
    assert runner.apps_root() == tmp_path / "apps"


def test_video_choice_is_rated_never_refused():
    big = images.choose_video(
        spec(ram=64, cores=16, gpus=[GPU("nvidia", "RTX 4090", 24 * G, 23 * G, False, "cuda")])
    )
    assert (
        big.kind == "video"
        and big.te_flag == "--t5xxl"
        and big.diffusion["quant"] == "Q8_0"
        and big.fits
    )
    mid = images.choose_video(
        spec(ram=32, cores=8, gpus=[GPU("nvidia", "RTX 4060", 8 * G, 7 * G, False, "cuda")])
    )
    assert mid.offload and mid.fits and mid.speed == "slow" and mid.diffusion["quant"] == "Q3_K_S"
    small = images.choose_video(spec(ram=8, cores=4, gpus=[]))
    assert not small.fits and small.speed == "crawl" and "still try" in " ".join(small.reasons)
    assert images.local_path(big.vae).name == "wan2.2_vae.safetensors"
    args = images.SdServer(Config()).args(mid, spec(ram=32, cores=8), 8422)
    assert "--t5xxl" in args and "--offload-to-cpu" in args
    assert images.recipe_of(big)["frames"] == 33


def test_guide_answers_without_any_ai_and_starter_exists():
    from datas.catalog import load as load_catalog
    from datas.orchestrator import STARTER_ID, STARTER_QUANT
    from datas.server.app import app

    f = load_catalog().get(STARTER_ID).file(STARTER_QUANT)
    assert f.bytes < 600 * 2**20
    roles = {m.role for m in load_catalog().models}
    assert {"math", "legal", "medical"} <= roles
    with TestClient(app) as c:
        r = c.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "What can my computer do?"}],
                "skill": "guide",
                "lang": "en",
            },
        )
        assert r.status_code == 200 and "Your device:" in r.text and "no AI yet" in r.text
        assert (
            c.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code
            == 503
        )
        j = c.get("/api/recommend", params={"use": "text", "role": "math", "context": 4096}).json()
        assert all("abilities" in j for _ in [0])
        apps = c.get("/api/apps").json()["apps"]
        assert {a["id"] for a in apps} >= {"comfyui", "facefusion"} and all(
            a["verdict"] in {"yes", "slow", "no"} for a in apps
        )
