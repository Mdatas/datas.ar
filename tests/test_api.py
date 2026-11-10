from fastapi.testclient import TestClient

from datas.server.app import app

client = TestClient(app)


def test_ui_served():
    r = client.get("/")
    assert r.status_code == 200 and "Datas" in r.text and "/ui/app.js" in r.text
    assert "/api/recommend" in client.get("/ui/screens.js").text


def test_spec_and_recommend():
    s = client.get("/api/spec").json()
    assert s["ram_total"] > 0 and "default_headroom" in s
    rec = client.get("/api/recommend", params={"context": 4096}).json()
    assert "budget" in rec and isinstance(rec["fits"], list)


def test_catalog_endpoint():
    c = client.get("/api/catalog").json()
    assert len(c["models"]) >= 15


def test_settings_roundtrip():
    r = client.post("/api/settings", json={"headroom": 0.3, "context": 4096, "lang": "es"}).json()
    assert r["headroom"] == 0.3 and r["context"] == 4096 and r["lang"] == "es"
    client.post("/api/settings", json={"headroom": 0.25, "context": 8192, "lang": "en"})


def test_proxy_without_model_is_503():
    r = client.post(
        "/v1/chat/completions",
        json={"model": "datas", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 503
    assert r.json()["error"]["type"] == "datas_no_model"


def test_providers_crud():
    r = client.post(
        "/api/providers",
        json={
            "name": "test-remote",
            "base_url": "http://127.0.0.1:1/v1",
            "api_key": "k",
            "model": "m",
        },
    )
    assert r.status_code == 200
    names = [p["name"] for p in client.get("/api/providers").json()["providers"]]
    assert "test-remote" in names
    assert (
        client.post("/api/providers/active", json={"name": "test-remote"}).json()["active"]
        == "test-remote"
    )
    client.post("/api/providers/active", json={"name": "local"})
    assert client.delete("/api/providers/test-remote").json()["ok"]
