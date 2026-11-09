"""The Datas guide briefing is built from live facts only and stays within a small model's context."""

from __future__ import annotations

from fastapi.testclient import TestClient

from datas.server.app import app


def test_guide_briefing_and_starters():
    with TestClient(app) as c:
        j = c.get("/api/guide?lang=en").json()
        b = j["briefing"]
        assert len(j["starters"]) >= 4 and all("?" in q for q in j["starters"])
        for section in (
            "FACTS ABOUT THIS DEVICE",
            "WHAT THIS DEVICE CAN DO",
            "RECOMMENDED FOR THIS DEVICE",
            "VOICE",
            "PRIVACY",
        ):
            assert section in b
        assert "Never invent" in b and len(b) < 16000  # ~4k tokens max
        es = c.get("/api/guide?lang=es").json()["briefing"]
        assert (
            "Answer in Spanish" in es and "¿" in c.get("/api/guide?lang=es").json()["starters"][0]
        )
        skills = c.get("/api/skills").json()["skills"]
        assert skills[0]["id"] == "guide"
