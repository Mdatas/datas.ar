"""What the backend says to the person, in English and Spanish (datas/words.py)."""

from __future__ import annotations

import ast
import string
from pathlib import Path

import pytest

from datas import words
from datas.things import ThingError, local, net
from datas.words import ES, Problem, Said, tr

ROOT = Path(__file__).resolve().parent.parent / "datas"
SAYERS = {"ThingError", "Problem", "Said", "tr"}  # calls whose first argument is a sentence


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_both_languages_name_the_same_values():
    for en, es in ES.items():
        assert es.strip(), en
        assert fields(en) == fields(es), f"{en!r} and its Spanish use different values"
    assert len(ES) > 120


def sentences_in_code() -> dict[str, str]:
    """Every sentence written straight into a ThingError / Problem / Said / tr call."""
    found = {}
    for path in sorted(ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            first = node.args[0]
            if name in SAYERS and isinstance(first, ast.Constant) and isinstance(first.value, str):
                found[first.value] = f"{path.relative_to(ROOT.parent)}:{node.lineno}"
    return found


def test_every_sentence_the_backend_says_has_its_spanish():
    found = sentences_in_code()
    assert len(found) > 60  # the scan really finds them
    missing = {where: text for text, where in found.items() if text not in ES}
    assert not missing, f"no Spanish for: {missing}"


def test_the_small_word_lists_have_their_spanish_too():
    from datas.things import control

    lists = (
        list(net.KINDS.values()),
        list(local.USB_MAKERS.values()),
        list(net.MODBUS_ERRORS.values()),
        ["serial device", "device that announces itself (UPnP)", "no picture came out"],
        [local.NEEDS_FFMPEG],
    )
    for group in lists:
        for text in group:
            assert text in ES, text
    for action in control.ACTIONS:  # each action is described in both languages
        en = control.describe(action, 1, 2, "hola", "ctrl+s", 3)
        es = control.describe(action, 1, 2, "hola", "ctrl+s", 3, lang="es")
        assert en != es and en and es, action


def test_a_sentence_is_said_again_in_spanish_with_its_values():
    e = ThingError("There is no printer called {name}. Found: {names}", name="'HP'", names="A, B")
    assert str(e) == "There is no printer called 'HP'. Found: A, B"
    assert e.say("es") == "No hay ninguna impresora llamada 'HP'. Encontradas: A, B"
    assert isinstance(e, RuntimeError) and e.say("fr") == str(e)  # unknown language: English
    # a value that is itself a sentence is translated too
    inner = Problem("The FFmpeg download did not contain the program.")
    outer = ThingError("The camera needs FFmpeg. {why}", why=inner)
    assert (
        outer.say("es") == "La cámara necesita FFmpeg. La descarga de FFmpeg no traía el programa."
    )
    assert str(outer) == "The camera needs FFmpeg. The FFmpeg download did not contain the program."
    refused = ThingError("The device refused: {why}.", why="the device is busy")
    assert refused.say("es") == "El aparato se negó: el aparato está ocupado."
    # a report of what was done is a normal string that can also be said in Spanish
    done = Said("Sent {name} to the printer {printer}.", name="a.pdf", printer="HP")
    assert done == "Sent a.pdf to the printer HP." and done.upper().startswith("SENT")
    assert done.say("es") == "Se envió a.pdf a la impresora HP."
    assert words.say(done, "es") == done.say("es") and words.say("printer", "es") == "impresora"
    assert words.say(ValueError("x"), "es") == "x"
    # odd input never breaks a message
    assert tr("Missing {value}", "es") == "Missing {value}"
    assert tr("{a} and {b}", "en", a=1) == "{a} and {b}"
    assert tr("Type: {text}", "es", text="hola") == "Escribir: hola"  # a value called "text"


def test_the_service_answers_in_the_language_datas_is_set_to(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    from fastapi.testclient import TestClient

    from datas.server import app as server

    client = TestClient(server.app, base_url="http://127.0.0.1")
    monkeypatch.setattr(server.core.cfg, "lang", "es")
    monkeypatch.setattr(local, "cameras", lambda fetch=False: [])
    monkeypatch.setattr(local, "_ffmpeg", lambda fetch=False, progress=None: "ffmpeg")
    r = client.post("/api/things/camera/photo", json={})
    assert (
        r.status_code == 409
        and r.json()["detail"] == "No se encontró ninguna cámara en esta computadora."
    )
    r = client.post("/api/things/print", json={})
    assert r.status_code == 400 and r.json()["detail"] == "No hay nada para imprimir."
    r = client.get("/api/status", headers={"host": "evil.example"})
    assert r.status_code == 403 and r.json()["detail"].startswith("Datas no responde")
    r = client.post("/api/things/check", json={"what": "mqtt"})
    assert r.json() == {
        "ok": False,
        "detail": ES[next(k for k in ES if k.startswith("No MQTT broker"))],
    }
    monkeypatch.setattr(server.core.cfg, "lang", "en")
    r = client.post("/api/things/camera/photo", json={})
    assert r.json()["detail"] == "No camera was found on this computer."


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_list_of_hardware_reads_in_the_persons_language(tmp_path, monkeypatch, lang):
    from datas import things
    from datas.things import control

    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    monkeypatch.setattr(
        local, "cameras", lambda: (_ for _ in ()).throw(ThingError(local.NEEDS_FFMPEG))
    )
    monkeypatch.setattr(local, "serial_ports", lambda: [{"port": "COM3", "what": "Arduino board"}])
    monkeypatch.setattr(local, "printers", lambda: [])
    monkeypatch.setattr(local, "screens", lambda: [])
    monkeypatch.setattr(
        control, "available", lambda: {"ok": False, "why": "there is no screen session"}
    )
    inv = things.inventory(lang)
    assert inv["serial"][0]["what"] == ("placa Arduino" if lang == "es" else "Arduino board")
    assert inv["control"]["why"] == (
        "no hay una sesión con pantalla" if lang == "es" else "there is no screen session"
    )
    assert inv["problems"]["cameras"].startswith(
        "La cámara necesita" if lang == "es" else "The camera needs"
    )
    assert set(inv["ffmpeg"]) == {"found", "bytes"}
