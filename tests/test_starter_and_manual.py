"""The starter AI at the device test, and the guide reading every document Datas ships."""

from fastapi.testclient import TestClient

from datas import manual
from datas.orchestrator import STARTER_ID, STARTER_QUANT


class _Job:
    def to_dict(self):
        return {"id": "j1"}


def test_starter_gets_the_small_ai_only_when_nothing_runs(monkeypatch):
    from datas.server import app as server

    asked = []
    monkeypatch.setattr(server.core, "start_run_job", lambda *a, **k: asked.append(a) or _Job())
    c = TestClient(server.app, base_url="http://127.0.0.1")
    monkeypatch.setattr(server.core.server, "running", lambda: False)
    assert c.post("/api/starter").json() == {"id": "j1"}
    assert asked[0][:3] == (STARTER_ID, STARTER_QUANT, 4096)
    monkeypatch.setattr(server.core.server, "running", lambda: True)
    assert "skipped" in c.post("/api/starter").json()
    assert len(asked) == 1


def test_the_guide_has_every_shipped_document():
    names = [d["name"] for d in manual.docs_text("en")]
    for doc in ("README", "ARCHITECTURE", "SURVIVAL", "CREDITS"):
        assert any(n.startswith("Datas documentation") and doc in n for n in names), doc
    assert names[0].startswith("Datas — Learn lessons (en)")
    assert manual.docs_text("es")[0]["name"].endswith("(es)")
