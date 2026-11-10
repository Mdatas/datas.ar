"""v0.2: plain-language layer, privacy modes, library, chats/context, agent page."""

import base64

from fastapi.testclient import TestClient

from datas.catalog import load
from datas.catalog.compare import TIERS, comparable
from datas.recommend.engine import headroom_for_mode, wants_for
from datas.server.app import app
from tests.conftest import spec

client = TestClient(app)


def test_every_model_has_plain_language_fields():
    for m in load().models:
        assert m.limits and len(m.limits) > 20, m.id
        assert m.vendor_url and m.vendor_url.startswith("https://"), m.id
        assert "text" in m.use_cases
        if "vision" in m.capabilities:
            assert "images" in m.use_cases


def test_comparable_tiers_cover_1_to_5():
    for t in range(1, 6):
        c = comparable(t)
        assert (
            c["openai"] and c["google"] and c["anthropic"] and "not a benchmark" in c["disclaimer"]
        )
    assert set(TIERS) == {1, 2, 3, 4, 5}


def test_use_case_mapping_and_modes():
    want, unsupported = wants_for(["text", "images", "sound", "coding", "video"])
    assert want == ["vision", "coding"] and unsupported == ["video"]  # sound = voice engines
    s = spec(ram=16)
    assert (
        headroom_for_mode(s, "light")
        > headroom_for_mode(s, "balanced")
        > headroom_for_mode(s, "heavy")
    )
    assert headroom_for_mode(spec(ram=8, form="phone"), "heavy") >= 0.08


def test_recommend_simple_params():
    r = client.get(
        "/api/recommend", params={"use": "text,sound", "mode": "light", "context": 4096}
    ).json()
    # "sound" is served by the voice engines; it is unsupported only when their packages are absent
    assert r["unsupported_use_cases"] in ([], ["sound"])
    if not r["unsupported_use_cases"]:
        assert r["voice"]["stt_model"] in {"tiny", "base", "small", "large-v3-turbo-q5_0"}
        assert r["voice"]["total_bytes"] > 100_000_000
    assert r["headroom"] >= 0.4
    if r["default"]:
        p = r["default"]["plain"]
        assert (
            p["comparable"]["openai"]
            and p["limits"]
            and p["model_page"].startswith("https://huggingface.co/")
        )


def test_privacy_modes_and_memory():
    r = client.post("/api/privacy", json={"memory_mode": "forget", "onboarded": True}).json()
    assert r["memory_mode"] == "forget" and r["keep_logs"] is False
    assert client.get("/api/chats").json()["forget"] is True
    assert (
        client.post("/api/chats", json={"messages": [{"role": "user", "content": "x"}]}).json()[
            "saved"
        ]
        is False
    )
    assert client.put("/api/memory", json={"text": "a"}).status_code == 400
    r = client.post("/api/privacy", json={"memory_mode": "remember"}).json()
    assert r["memory_mode"] == "remember"
    saved = client.post(
        "/api/chats",
        json={
            "messages": [
                {"role": "user", "content": "hello there"},
                {"role": "assistant", "content": "hi"},
            ]
        },
    ).json()
    assert saved["saved"] and saved["chat_id"]
    assert any(c["id"] == saved["chat_id"] for c in client.get("/api/chats").json()["chats"])
    assert client.put("/api/memory", json={"text": "- likes tea"}).json()["ok"]
    assert "tea" in client.get("/api/memory").json()["text"]
    assert client.post("/api/privacy/wipe").json()["chats_deleted"] >= 1
    assert client.get("/api/memory").json()["text"] == ""


def test_context_files_roundtrip():
    b64 = base64.b64encode(b"Datas test").decode()
    r = client.post("/api/context", json={"name": "notes.txt", "content_base64": b64}).json()
    assert r["bytes"] == 10
    names = [f["name"] for f in client.get("/api/context").json()["files"]]
    assert "notes.txt" in names
    assert client.delete("/api/context/notes.txt").json()["deleted"]


def test_sources_skills_library_agent_page():
    s = client.get("/api/sources").json()
    assert s["project"]["repo"].startswith("https://github.com/") and len(s["sources"]) >= 15
    assert all(x["url"].startswith("http") for x in s["sources"])
    sk = client.get("/api/skills").json()["skills"]
    assert {"summarize", "translate", "plain"} <= {x["id"] for x in sk}
    lib = client.get("/api/library").json()
    assert "installed" in lib and "running" in lib
    assert client.get("/agent").status_code == 200
    assert (
        client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code
        == 503
    )


def test_ui_has_simple_flow_and_translations():
    from tests import ui_keys

    d = ui_keys.dictionary()
    # the first-run choices, the one-button start and the plain verdicts exist in both languages
    for key in ("mode_remember", "mode_forget", "get_this", "f_like", "use_images", "nav_about"):
        assert d["en"][key] and d["es"][key] and d["en"][key] != d["es"][key]
    assert d["en"]["mode_forget"] == "Forget" and d["es"]["mode_forget"] == "Olvidar"
    assert 'src="/ui/i18n.js"' in client.get("/").text
