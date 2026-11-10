"""Linked devices: pairing by one-time code, mutual TLS with pinned certificates, chat sync,
and carrying on alone when a device goes away."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from datas import chats, link


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- the pieces ---------------------------------------------------------------------


def test_codes_addresses_and_proofs():
    code = link.new_code()
    assert len(code) == link.CODE_LEN and set(code) <= set(link.ALPHABET)
    assert not set("01IO") & set(link.ALPHABET)  # nothing that looks like something else
    assert link.clean_code(link.pretty_code(code).lower()) == code
    assert link.split_address("192.168.1.20", 8424) == ("192.168.1.20", 8424)
    assert link.split_address(" 192.168.1.20:9000 ", 8424) == ("192.168.1.20", 9000)
    assert link.split_address("[fe80::1]:9000", 8424) == ("fe80::1", 9000)
    with pytest.raises(link.LinkError):
        link.split_address("host:notaport", 8424)
    salt = os.urandom(32)
    k = link.derive(code, salt)
    assert k == link.derive(link.pretty_code(code), salt) and k != link.derive("A" * 12, salt)
    n1, n2 = os.urandom(16), os.urandom(16)
    p = link.proof(k, b"client", "aa", "bb", n1, n2)
    assert p != link.proof(k, b"server", "aa", "bb", n1, n2)  # roles cannot be replayed
    assert p != link.proof(k, b"client", "aa", "cc", n1, n2)  # bound to both certificates


def test_only_the_pinned_certificate_is_accepted(tmp_path):
    ka, ca, pem_a = link.ensure_identity("A", tmp_path / "a")
    kb, cb, pem_b = link.ensure_identity("B", tmp_path / "b")
    kc, cc, pem_c = link.ensure_identity("C", tmp_path / "c")
    assert link.ensure_identity("A", tmp_path / "a")[2] == pem_a  # kept, not remade
    assert len({link.fingerprint(p) for p in (pem_a, pem_b, pem_c)}) == 3

    async def run() -> dict:
        seen = {}

        async def handle(reader, writer):
            der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            seen["client"] = link.fingerprint(ssl.DER_cert_to_PEM_cert(der)) if der else None
            await link.send(writer, {"hello": "ok"})
            writer.close()

        # A's server knows B only
        srv = await asyncio.start_server(
            handle, "127.0.0.1", 0, ssl=link.server_context(ka, ca, [pem_b])
        )
        port = srv.sockets[0].getsockname()[1]
        out = {}
        # B, pinning A: works, and A sees exactly B
        r, w = await asyncio.open_connection(
            "127.0.0.1", port, ssl=link.client_context(kb, cb, pem_a)
        )
        out["b"] = await link.recv(r)
        out["tls"] = w.get_extra_info("ssl_object").version()
        w.close()
        out["b_seen_as"] = seen.get("client")
        # C (never paired) presenting its own certificate: refused by A
        try:
            r, w = await asyncio.open_connection(
                "127.0.0.1", port, ssl=link.client_context(kc, cc, pem_a)
            )
            out["c"] = await link.recv(r)
        except (ssl.SSLError, ConnectionError, asyncio.IncompleteReadError, OSError) as e:
            out["c"] = type(e).__name__
        # B expecting a different device at that address (pins C): B refuses A
        try:
            await asyncio.open_connection("127.0.0.1", port, ssl=link.client_context(kb, cb, pem_c))
            out["wrong_pin"] = "connected"
        except ssl.SSLError:
            out["wrong_pin"] = "refused"
        srv.close()
        return out

    out = asyncio.run(run())
    assert out["b"] == {"hello": "ok"} and out["tls"] == "TLSv1.3"
    assert out["b_seen_as"] == link.fingerprint(pem_b)
    assert out["c"] != {"hello": "ok"}
    assert out["wrong_pin"] == "refused"


def test_newest_change_wins_and_deletions_stick(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    now = time.time()
    base = {"id": "c1", "title": "t", "messages": [{"role": "user", "content": "v1"}]}
    assert chats.apply_remote_chat(base | {"updated": now - 100})
    assert not chats.apply_remote_chat(base | {"updated": now - 200})  # older: ignored
    newer = base | {"updated": now - 50, "messages": [{"role": "user", "content": "v2"}]}
    assert chats.apply_remote_chat(newer)
    assert chats.load_chat("c1")["messages"][0]["content"] == "v2"
    assert chats.manifest() == {"c1": now - 50}
    # deleted elsewhere after the last change here → goes away and stays away
    assert chats.apply_tombstones({"c1": now - 10}) == 1
    assert chats.load_chat("c1") is None
    assert not chats.apply_remote_chat(newer)
    # ...but a change made after the deletion wins over it
    assert chats.apply_remote_chat(base | {"updated": now})
    assert chats.apply_tombstones({"c1": now - 10}) == 0 and chats.load_chat("c1")
    # nonsense from the network is ignored
    assert not chats.apply_remote_chat({"id": "../evil", "updated": "x"})
    assert not chats.apply_remote_chat({"id": "c2", "updated": now, "messages": "no"})


def test_carrying_on_alone_when_a_linked_device_goes_away(monkeypatch):
    from datas import library
    from datas.orchestrator import Datas
    from datas.runtime import downloader

    core = Datas()
    started = []
    monkeypatch.setattr(core.server, "stop", lambda *a, **k: None)
    monkeypatch.setattr(core, "run", lambda mid, q, *a, **k: started.append((mid, q)) or {})
    fits = [c for c in core.recommendation().fits if c.role == "general"]
    assert fits, "the test machine must fit at least the smallest model"
    small = fits[-1]
    monkeypatch.setattr(
        library, "installed", lambda: [{"model_id": small.model_id, "custom": False}]
    )
    monkeypatch.setattr(
        downloader, "is_downloaded", lambda m, f: m.id == small.model_id and f.quant == small.quant
    )
    n = core.fallback_local("Desk PC")
    assert n["kind"] == "fallback" and started == [(small.model_id, small.quant)]
    assert "Desk PC" in n["text"] and small.name in n["text"]
    # nothing installed fits alone → a clear message, not a crash
    monkeypatch.setattr(library, "installed", lambda: [])
    assert core.fallback_local("Desk PC")["kind"] == "fallback_none"


# ---- two real instances talking to each other ------------------------------------------


class Instance:
    def __init__(self, tmp: Path, name: str):
        self.home = tmp / name
        self.home.mkdir()
        self.ui, self.link = free_port(), free_port()
        (self.home / "config.json").write_text(
            json.dumps(
                {
                    "ui_port": self.ui,
                    "link_port": self.link,
                    "llama_port": free_port(),
                    "rpc_port": free_port(),
                    "memory_mode": "remember",
                    "onboarded": True,
                    "device_name": f"Device {name}",
                }
            )
        )
        env = dict(os.environ, DATAS_HOME=str(self.home))
        code = (
            "import uvicorn\n"
            "from datas.server.app import app, set_http_port\n"
            f"set_http_port({self.ui})\n"
            f"uvicorn.run(app, host='127.0.0.1', port={self.ui}, log_level='error')\n"
        )
        self.proc = subprocess.Popen(
            [sys.executable, "-c", code],
            env=env,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.http = httpx.Client(
            base_url=f"http://127.0.0.1:{self.ui}", trust_env=False, timeout=60
        )

    def wait(self) -> None:
        for _ in range(150):
            try:
                if self.http.get("/api/privacy").status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise RuntimeError("instance did not start")

    def stop(self) -> None:
        self.http.close()
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


@pytest.fixture
def two(tmp_path):
    a, b = Instance(tmp_path, "A"), Instance(tmp_path, "B")
    try:
        a.wait()
        b.wait()
        yield a, b
    finally:
        a.stop()
        b.stop()


def test_pair_sync_and_refuse_strangers(two):
    a, b = two
    st = a.http.post("/api/link/pairing").json()
    code = st["pairing"]["code"]
    assert st["enabled"] and len(code) == 14 and st["pairing"]["expires_in"] > 500
    addr = f"127.0.0.1:{a.link}"
    # a wrong code links nothing
    bad = b.http.post("/api/link/pair", json={"address": addr, "code": "AAAA-BBBB-CCCC"})
    assert bad.status_code == 400 and b.http.get("/api/link").json()["peers"] == []
    # nobody listening at that address: a sentence, not a stack trace
    nowhere = b.http.post(
        "/api/link/pair", json={"address": f"127.0.0.1:{free_port()}", "code": code}
    )
    assert nowhere.status_code == 400 and "Could not reach" in nowhere.json()["detail"]
    ok = b.http.post("/api/link/pair", json={"address": addr, "code": code})
    assert ok.status_code == 200, ok.text
    peer = ok.json()["peer"]
    assert peer["name"] == "Device A" and peer["online"]
    # the code worked once and is gone
    again = b.http.post("/api/link/pair", json={"address": addr, "code": code})
    assert again.status_code == 400
    assert a.http.get("/api/link").json()["pairing"] is None
    # both sides know each other, by certificate fingerprint
    ida = a.http.get("/api/link").json()["device"]["id"]
    idb = b.http.get("/api/link").json()["device"]["id"]
    assert peer["id"] == ida
    assert [p["id"] for p in a.http.get("/api/link").json()["peers"]] == [idb]

    # chats travel both ways; a deletion travels too
    c1 = a.http.post(
        "/api/chats", json={"messages": [{"role": "user", "content": "written on A"}]}
    ).json()["chat_id"]
    b.http.post("/api/chats", json={"messages": [{"role": "user", "content": "written on B"}]})
    assert b.http.post("/api/link/sync").json() == {"synced_with": ["Device A"], "errors": []}
    titles = lambda inst: sorted(c["title"] for c in inst.http.get("/api/chats").json()["chats"])  # noqa: E731
    assert titles(a) == titles(b) == ["written on A", "written on B"]
    b.http.delete(f"/api/chats/{c1}")
    a.http.get("/api/link", params={"refresh": 1})
    assert a.http.post("/api/link/sync").json()["errors"] == []
    assert titles(a) == ["written on B"]

    # a device that was never paired gets nothing — over TLS 1.3 all the same
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with ctx.wrap_socket(socket.create_connection(("127.0.0.1", a.link), timeout=10)) as s:
        assert s.version() == "TLSv1.3"
        msg = json.dumps({"op": "sync", "manifest": {}}).encode()
        s.sendall(len(msg).to_bytes(4, "big") + msg)
        n = int.from_bytes(s.recv(4), "big")
        reply = json.loads(s.recv(n))
    assert reply["ok"] is False and "not linked" in reply["error"]

    # unlinking closes the door for that device
    assert b.http.delete(f"/api/link/peers/{ida}").json()["removed"]
    assert a.http.delete(f"/api/link/peers/{idb}").json()["removed"]
    assert a.http.get("/api/link").json()["peers"] == []


def test_the_ai_on_a_linked_device_needs_a_link(two):
    a, _ = two
    r = a.http.post("/api/link/use/" + "0" * 64)
    assert r.status_code == 404
    r = a.http.post("/link/" + "0" * 64 + "/v1/chat/completions", json={"messages": []})
    assert r.status_code == 502 and r.json()["error"]["type"] == "datas_link"


def test_a_computer_opens_the_datas_of_another_computer_only_when_allowed(two):
    """A computer without a screen (A) is looked after from the laptop (B): B shows A's Datas
    through the encrypted link — once someone at A allowed it, and with a phone's limits."""
    a, b = two
    code = a.http.post("/api/link/pairing").json()["pairing"]["code"]
    peer = b.http.post(
        "/api/link/pair", json={"address": f"127.0.0.1:{a.link}", "code": code}
    ).json()["peer"]
    ida, idb = peer["id"], b.http.get("/api/link").json()["device"]["id"]
    assert peer["window"] is False  # nothing is open between two computers until it is asked

    # not allowed yet: a sentence that says where to switch it on
    no = b.http.post(f"/api/link/peers/{ida}/open", json={"show": False})
    assert no.status_code == 400
    assert "Device A has not allowed this computer" in no.json()["detail"]
    assert 'datas-cli link window "Device B" on' in no.json()["detail"]

    # someone at A allows B
    on = a.http.post(f"/api/link/peers/{idb}", json={"window": True}).json()
    assert on["window"] is True and on["kind"] == "device"
    r = b.http.post(f"/api/link/peers/{ida}/open", json={"show": False})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["name"] == "Device A" and out["shown"] is False
    assert out["url"].startswith("http://127.0.0.1:")
    # asking again gives the same door, not a new one each time
    assert b.http.post(f"/api/link/peers/{ida}/open", json={"show": False}).json() == out

    with httpx.Client(base_url=out["url"], trust_env=False, timeout=30) as door:
        st = door.get("/api/status").json()
        assert st["remote"] == {"device": "Device A", "phone": "Device B", "kind": "device"}
        assert "/ui/app.js" in door.get("/").text
        # A's chats, written from B's window, are kept on A
        saved = door.post(
            "/api/chats", json={"messages": [{"role": "user", "content": "from the laptop"}]}
        )
        assert saved.status_code == 200
        assert [c["title"] for c in a.http.get("/api/chats").json()["chats"]] == ["from the laptop"]
        # the limits of a phone apply: nothing that acts on A itself
        for method, path, body in (
            ("POST", "/api/shutdown", {}),
            ("POST", "/api/link/pairing", {}),
            ("POST", f"/api/link/peers/{idb}", {"window": True}),
            ("GET", "/api/things", None),
            ("POST", "/api/agent/run", {"task": "x", "allow_shell": True}),
        ):
            refused = door.request(method, path, json=body)
            assert refused.status_code == 403, (path, refused.status_code)
            assert "linked device" in refused.json()["detail"], path
        assert "remote" not in a.http.get("/api/status").json()  # at A itself: not remote

        # A takes it back: the door leads nowhere and asking again is refused
        a.http.post(f"/api/link/peers/{idb}", json={"window": False})
        with pytest.raises(httpx.HTTPError):
            httpx.get(out["url"] + "api/status", trust_env=False, timeout=10)
    again = b.http.post(f"/api/link/peers/{ida}/open", json={"show": False})
    assert again.status_code == 400 and "has not allowed" in again.json()["detail"]
    # a phone never has a Datas to open; an unknown device is said plainly
    assert b.http.post("/api/link/peers/nobody/open", json={"show": False}).status_code == 400
