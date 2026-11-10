"""A phone linked to a computer: pairing with a secret instead of a certificate, the
computer's Datas window through the encrypted link, and what a phone is refused."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from datas import link
from datas.server.app import remote_refusal

from . import phone
from .test_link import Instance

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def computer(tmp_path):
    a = Instance(tmp_path, "A")
    try:
        a.wait()
        yield a
    finally:
        a.stop()


def test_what_is_refused_from_a_phone():
    no = remote_refusal
    assert no("POST", "/api/shutdown") and no("POST", "/api/open") and no("POST", "/api/open-url")
    assert no("POST", "/api/voice/listen/start") and no("GET", "/api/voice/listen/level")
    assert no("POST", "/api/link/pairing") and no("DELETE", "/api/link/peers/abc")
    assert no("POST", "/api/mcp") and no("POST", "/api/privacy/wipe")
    assert no("POST", "/api/programs/blender/open") and no("POST", "/api/updates/app")
    assert no("POST", "/api/things/camera/photo") and no("GET", "/api/things")
    # everyday use goes on
    for method, path in (
        ("GET", "/"),
        ("GET", "/ui/app.js"),
        ("GET", "/api/status"),
        ("POST", "/api/chat"),
        ("GET", "/api/link"),
        ("GET", "/api/programs"),
        ("POST", "/api/export"),
        ("POST", "/api/openness"),  # not "/api/open": only whole path parts count
        ("POST", "/api/updates/check"),
        ("POST", "/api/voice/speak"),
    ):
        assert no(method, path) is None, (method, path)


def test_a_phone_pairs_and_opens_the_computers_datas(computer):
    a = computer
    code = a.http.post("/api/link/pairing").json()["pairing"]["code"]
    with pytest.raises(link.LinkError):
        phone.pair("127.0.0.1", a.link, "AAAA-BBBB-CCCC")
    p = phone.pair("127.0.0.1", a.link, code, "Marta's phone", "android")
    assert p["name"] == "Device A" and len(p["id"]) == 64

    peers = a.http.get("/api/link").json()["peers"]
    assert len(peers) == 1 and peers[0]["kind"] == "app" and peers[0]["name"] == "Marta's phone"
    assert peers[0]["window"] is True and peers[0]["os"] == "android" and peers[0]["online"]
    # the computer keeps a fingerprint of the phone's secret, never the secret
    stored = (a.home / "link" / "peers.json").read_text()
    assert p["me"] in stored and p["secret"] not in stored
    # the code worked once
    with pytest.raises(link.LinkError):
        phone.pair("127.0.0.1", a.link, code)

    # how the computer is (name, version, whether an AI is ready)
    info, s = phone.ask(p, "info")
    s.close()
    assert info["ok"] and info["name"] == "Device A"

    # the computer's Datas, through the link
    status, body = phone.http(p, "GET", "/api/status")
    assert status == 200 and body["remote"] == {"device": "Device A", "phone": "Marta's phone"}
    assert "remote" not in a.http.get("/api/status").json()  # at the computer itself: not remote
    status, page = phone.http(p, "GET", "/")
    assert status == 200 and "/ui/app.js" in page
    assert phone.http(p, "GET", "/api/learn?lang=es")[0] == 200
    status, saved = phone.http(
        p, "POST", "/api/chats", {"messages": [{"role": "user", "content": "hola"}]}
    )
    assert status == 200 and (saved.get("chat_id") or saved.get("id"))

    # what a phone may not do there
    for method, path, body in (
        ("POST", "/api/shutdown", {}),
        ("POST", "/api/link/pairing", {}),
        ("POST", "/api/voice/listen/start", {}),
        ("POST", "/api/open-url", {"url": "https://example.org"}),
        ("POST", "/api/mcp", {"name": "x", "command": "calc"}),
        ("POST", "/api/agent/run", {"task": "x", "allow_shell": True}),
    ):
        status, out = phone.http(p, method, path, body)
        assert status == 403, (path, status, out)
    assert a.http.get("/api/privacy").status_code == 200  # …and the computer is still up

    # a phone cannot use the requests meant for computers
    for op in ("sync", "rpc", "v1"):
        r, s = phone.ask(p, op)
        s.close()
        assert not r.get("ok")
    # a made-up secret is nobody
    r, s = phone.ask({**p, "secret": "00" * 32}, "window")
    s.close()
    assert not r.get("ok")

    # the owner can close that door at the computer, or unlink the phone
    pid = peers[0]["id"]
    assert a.http.post(f"/api/link/peers/{pid}", json={"window": False}).json()["window"] is False
    with pytest.raises(link.LinkError):
        phone.http(p, "GET", "/api/status")
    a.http.post(f"/api/link/peers/{pid}", json={"window": True})
    assert phone.http(p, "GET", "/api/status")[0] == 200
    assert a.http.delete(f"/api/link/peers/{pid}").json()["removed"]
    r, s = phone.ask(p, "info")
    s.close()
    assert not r.get("ok")


# ---- the Android app's own link code (plain Java), against a real Datas ----------------

JAVA_SOURCES = sorted((ROOT / "android/app/src/main/java/ar/datas/link").glob("*.java"))
JAVA_CLI = ROOT / "android/link-cli/LinkCli.java"


@pytest.fixture(scope="module")
def java(tmp_path_factory):
    if not (shutil.which("javac") and shutil.which("java")):
        pytest.skip("no Java compiler on this machine")
    out = tmp_path_factory.mktemp("java")
    r = subprocess.run(
        ["javac", "-d", str(out), *map(str, JAVA_SOURCES), str(JAVA_CLI)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["java", "-cp", str(out), "LinkCli", *args], capture_output=True, text=True, timeout=120
        )

    return run


def test_the_android_link_code_talks_to_a_real_datas(computer, java):
    a = computer
    code = a.http.post("/api/link/pairing").json()["pairing"]["code"]
    wrong = java("pair", "127.0.0.1", str(a.link), "AAAA-BBBB-CCCC", "Java phone")
    assert wrong.returncode == 2 and "LINK:" in wrong.stdout
    r = java("pair", "127.0.0.1", str(a.link), code, 'Phone "J" ñ')
    assert r.returncode == 0, r.stdout + r.stderr
    remembered = r.stdout.strip().splitlines()[-1]
    assert '"name":"Device A"' in remembered
    peers = a.http.get("/api/link").json()["peers"]
    assert [(p["kind"], p["name"]) for p in peers] == [("app", 'Phone "J" ñ')]

    assert '"name":"Device A"' in java("info", remembered).stdout

    got = java("get", remembered, "/api/status")
    status, _, body = got.stdout.partition("\n")
    assert status.strip() == "200", got.stdout + got.stderr
    assert '"device":"Device A"' in body.replace(": ", ":")
    # a real page and a script file come through whole
    page = java("get", remembered, "/ui/app.js").stdout
    assert page.startswith("200") and "function renderShell" in page
    # sending something, and being refused where a phone should be
    saved = java(
        "post", remembered, "/api/chats", '{"messages":[{"role":"user","content":"hola"}]}'
    )
    assert saved.stdout.startswith("200") and "chat_id" in saved.stdout
    assert java("post", remembered, "/api/shutdown", "{}").stdout.startswith("403")

    # the computer's certificate is pinned: another Datas at that address is not accepted
    b = Instance(a.home.parent, "B")
    try:
        b.wait()
        b.http.post("/api/link/enable", json={"on": True})
        elsewhere = remembered.replace(f'"port":{a.link}', f'"port":{b.link}')
        assert elsewhere != remembered
        out = java("info", elsewhere)
        assert out.returncode == 2 and "not the computer that was linked" in out.stdout
        # through the door the person sees a plain page, not an error code
        door = java("get", elsewhere, "/api/status").stdout
        assert door.startswith("502") and "Not connected" in door
    finally:
        b.stop()

    # unlinked at the computer: the phone is turned away
    assert a.http.delete(f"/api/link/peers/{peers[0]['id']}").json()["removed"]
    assert java("info", remembered).returncode == 2
