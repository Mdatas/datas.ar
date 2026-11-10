"""A phone, as far as the link is concerned — written out in plain Python.

This is the reference for the Android (Java) and iPhone (Swift) clients: the same messages,
in the same order. See the top of datas/link/__init__.py for why it is safe.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import ssl

from datas import link


def _tls(host: str, port: int) -> ssl.SSLSocket:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # the certificate is checked by fingerprint, below
    return ctx.wrap_socket(socket.create_connection((host, port), timeout=15))


def _send(s: ssl.SSLSocket, obj: dict) -> None:
    data = json.dumps(obj).encode()
    s.sendall(len(data).to_bytes(4, "big") + data)


def _exactly(s: ssl.SSLSocket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def _recv(s: ssl.SSLSocket) -> dict:
    return json.loads(_exactly(s, int.from_bytes(_exactly(s, 4), "big")))


def fingerprint_of(s: ssl.SSLSocket) -> str:
    return hashlib.sha256(s.getpeercert(binary_form=True)).hexdigest()


def pair(
    host: str, port: int, code: str, name: str = "Test phone", os_name: str = "android"
) -> dict:
    """Returns what the phone keeps: the computer's fingerprint and name, and its own secret."""
    secret = os.urandom(32)
    me = hashlib.sha256(secret).hexdigest()
    s = _tls(host, port)
    try:
        computer = fingerprint_of(s)
        n_c = os.urandom(16)
        _send(
            s,
            {"op": "pair", "app": True, "id": me, "name": name, "os": os_name, "nonce": n_c.hex()},
        )
        r = _recv(s)
        if not r.get("ok"):
            raise link.LinkError(r.get("error", "refused"))
        n_s = bytes.fromhex(r["nonce"])
        key = link.derive(code, n_c + n_s)
        _send(s, {"proof": link.proof(key, b"client", me, computer, n_c, n_s).hex()})
        r2 = _recv(s)
        if not r2.get("ok"):
            raise link.LinkError(r2.get("error", "wrong code"))
        want = link.proof(key, b"server", computer, me, n_s, n_c)
        if not hmac.compare_digest(want, bytes.fromhex(r2.get("proof", ""))):
            raise link.LinkError("the computer could not prove it knows the code")
        return {
            "id": computer,
            "name": r.get("name", ""),
            "host": host,
            "port": port,
            "secret": secret.hex(),
            "me": me,
        }
    finally:
        s.close()


def ask(peer: dict, op: str, **more) -> tuple[dict, ssl.SSLSocket]:
    """One request to the linked computer; the connection is returned open (for "window")."""
    s = _tls(peer["host"], peer["port"])
    if fingerprint_of(s) != peer["id"]:
        s.close()
        raise link.LinkError("that is not the computer this phone was linked to")
    _send(s, {"op": op, "auth": peer["secret"], **more})
    return _recv(s), s


def http(peer: dict, method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    """A web request to the computer's Datas, through the link."""
    r, s = ask(peer, "window")
    if not r.get("ok"):
        s.close()
        raise link.LinkError(r.get("error", "refused"))
    try:
        data = json.dumps(body).encode() if body is not None else b""
        head = f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n"
        if body is not None:
            head += f"Content-Type: application/json\r\nContent-Length: {len(data)}\r\n"
        s.sendall(head.encode() + b"\r\n" + data)
        raw = b""
        while True:
            try:
                chunk = s.recv(65536)
            except (ssl.SSLError, ConnectionError):
                break
            if not chunk:
                break
            raw += chunk
        head_b, _, payload = raw.partition(b"\r\n\r\n")
        status = int(head_b.split(b" ", 2)[1])
        if b"transfer-encoding: chunked" in head_b.lower():
            out, rest = b"", payload
            while rest:
                size, _, rest = rest.partition(b"\r\n")
                n = int(size.split(b";")[0] or b"0", 16)
                if n == 0:
                    break
                out, rest = out + rest[:n], rest[n + 2 :]
            payload = out
        try:
            return status, json.loads(payload)
        except ValueError:
            return status, payload.decode("utf-8", "replace")
    finally:
        s.close()
