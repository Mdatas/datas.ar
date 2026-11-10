"""Linking the user's own devices — encrypted, authenticated, with nothing in the middle.

What it is for
    * add up the memory of several devices so a bigger AI fits (llama.cpp RPC through a tunnel);
    * use the AI that is running on another of your devices (a small laptop asks the desktop);
    * keep chats in step between devices (Remember mode only).

How two devices become linked (once)
    Device A shows an address and a one-time code. On device B the user types both. The code
    itself never travels: each side proves it knows it, with an HMAC over both devices'
    certificate fingerprints and fresh random numbers, keyed by the code stretched with PBKDF2.
    A device in the middle that does not know the code cannot pass that test, and cannot swap
    in its own certificate, because the fingerprints are part of what is proven. Afterwards
    each device keeps the other's certificate and the code is thrown away.

How they talk from then on
    TLS 1.3 with a certificate on both sides ("mutual TLS"), each side accepting only the exact
    certificate it stored at pairing ("pinning"). No certificate authority, no account, no
    server run by anyone. The Wi-Fi router, the internet provider and other people on the same
    network see only encrypted traffic, and a device that was never paired cannot connect.

Phones and tablets (the Datas apps)
    A phone pairs with the same one-time code, but it brings no certificate of its own:
    it invents a long random secret and proves, with the code, that the secret is its.
    From then on it connects with TLS 1.3, accepts only this device's exact certificate,
    and shows its secret inside that encrypted connection. This device keeps only a
    fingerprint (SHA-256) of the secret. A linked phone can ask how this device is and —
    if you allow it — open this device's Datas window through the link ("window" below).
    It cannot pair other devices, lend or borrow memory, or reach anything else.

See docs/DEVICES.md for the plain-language version and the limits.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from datas import __version__, chats
from datas.config import home

PROTO = b"datas-link-v1"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I: easy to read aloud and type
CODE_LEN = 12  # 12 symbols of 32 = 60 bits
CODE_TTL = 600  # seconds a pairing code stays valid
MAX_TRIES = 5  # wrong proofs before the code is cancelled
PBKDF2_ITERS = 300_000
MAX_FRAME = 64 * 2**20
BUF = 1 << 20
V1_PATHS = {"chat/completions", "completions", "models", "embeddings"}


class LinkError(RuntimeError):
    """Something the user can act on: wrong code, device unreachable, not linked…"""


# ---------------------------------------------------------------------------
# identity: one key and one self-signed certificate per device
# ---------------------------------------------------------------------------


def link_dir(directory: Path | None = None) -> Path:
    p = directory or (home() / "link")
    p.mkdir(parents=True, exist_ok=True)
    return p


def fingerprint(cert_pem: str) -> str:
    """SHA-256 of the certificate: the device's identity (64 hex characters)."""
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert_pem)).hexdigest()


def short_id(device_id: str) -> str:
    return "-".join(device_id[i : i + 4] for i in range(0, 16, 4)).upper()


def ensure_identity(name: str, directory: Path | None = None) -> tuple[Path, Path, str]:
    """(key file, certificate file, certificate PEM); created on first use, then kept."""
    d = link_dir(directory)
    key_p, crt_p = d / "device.key", d / "device.crt"
    if key_p.exists() and crt_p.exists():
        try:
            pem = crt_p.read_text()
            fingerprint(pem)
            return key_p, crt_p, pem
        except (ValueError, OSError):
            pass
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, (name or "Datas device")[:60]),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Datas.ar device"),
        ]
    )
    pub = key.public_key()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(pub)
        .serial_number(x509.random_serial_number())
        # generous dates: a device with a wrong clock must still be able to link
        .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365 * 50))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(pub), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(pub), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_p.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(key_p, 0o600)
    except OSError:
        pass
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    crt_p.write_text(pem)
    return key_p, crt_p, pem


def server_context(key_p: Path, crt_p: Path, peer_certs: list[str]) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(str(crt_p), str(key_p))
    # A client may come without a certificate only to pair; anything else needs one of these.
    ctx.verify_mode = ssl.CERT_OPTIONAL
    for pem in peer_certs:
        try:
            ctx.load_verify_locations(cadata=pem)
        except ssl.SSLError:
            continue
    return ctx


def client_context(key_p: Path, crt_p: Path, peer_cert: str | None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = False  # devices are known by certificate, not by name
    if peer_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=peer_cert)  # only this exact certificate is accepted
        ctx.load_cert_chain(str(crt_p), str(key_p))
    else:
        # Pairing: the other device is not known yet. Its certificate is authenticated by the
        # proof exchanged right after (see pair()), not by the TLS layer.
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ---------------------------------------------------------------------------
# pairing math
# ---------------------------------------------------------------------------


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def pretty_code(code: str) -> str:
    return "-".join(code[i : i + 4] for i in range(0, len(code), 4))


def clean_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def derive(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", clean_code(code).encode(), PROTO + salt, PBKDF2_ITERS, 32)


def proof(key: bytes, role: bytes, fp_self: str, fp_other: str, n1: bytes, n2: bytes) -> bytes:
    msg = b"|".join(
        [PROTO, role, fp_self.encode(), fp_other.encode(), n1.hex().encode(), n2.hex().encode()]
    )
    return hmac.new(key, msg, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# framing: 4-byte length + JSON, then (for tunnels) raw bytes
# ---------------------------------------------------------------------------


async def send(writer: asyncio.StreamWriter, obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode()
    writer.write(len(data).to_bytes(4, "big") + data)
    await writer.drain()


async def recv(reader: asyncio.StreamReader, limit: int = MAX_FRAME) -> dict:
    n = int.from_bytes(await reader.readexactly(4), "big")
    if n > limit:
        raise LinkError("message too large")
    obj = json.loads(await reader.readexactly(n))
    if not isinstance(obj, dict):
        raise LinkError("unexpected message")
    return obj


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(BUF)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError, ssl.SSLError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            writer.close()
        except Exception:  # noqa: BLE001
            pass


async def splice(r1, w1, r2, w2) -> None:  # noqa: ANN001
    """Copy bytes both ways until either side closes."""
    await asyncio.gather(_pipe(r1, w2), _pipe(r2, w1))


def split_address(address: str, default_port: int) -> tuple[str, int]:
    a = address.strip().replace("http://", "").replace("https://", "").strip("/")
    if a.startswith("["):  # [ipv6]:port
        host, _, rest = a[1:].partition("]")
        port = rest.lstrip(":")
    elif a.count(":") == 1:
        host, _, port = a.partition(":")
    else:
        host, port = a, ""
    if not host:
        raise LinkError("type the address shown on the other device")
    try:
        return host, int(port) if port else default_port
    except ValueError as e:
        raise LinkError("the address should look like 192.168.1.20:8424") from e


def local_addresses() -> list[str]:
    """This device's addresses on the networks it is connected to (the usual one first)."""
    out: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; picks the default route's interface
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        import psutil

        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254.")):
                    if a.address not in out:
                        out.append(a.address)
    except Exception:  # noqa: BLE001
        pass
    return [a for a in out if not a.startswith("127.")]


# ---------------------------------------------------------------------------
# the manager
# ---------------------------------------------------------------------------

MDNS_TYPE = "_datas-link._tcp.local."


class LinkManager:
    """One per running Datas. Owns a small event loop in its own thread: the link server, the
    tunnels, the periodic check of linked devices and chat sync."""

    def __init__(self, core) -> None:  # noqa: ANN001 - Datas orchestrator
        self.core = core
        self.cfg = core.cfg
        self.name = self.cfg.device_name or socket.gethostname().split(".")[0] or "Datas device"
        self.key_p, self.crt_p, self.cert = ensure_identity(self.name)
        self.id = fingerprint(self.cert)
        self.pairing: dict | None = None
        self.status: dict[str, dict] = {}
        self.tunnels: dict[str, tuple[asyncio.AbstractServer, int]] = {}
        self.last_sync: float = 0.0
        self.sync_error: str = ""
        self._dirty = True
        self._peers = self._load_peers()
        self._server: asyncio.AbstractServer | None = None
        self._ctx: ssl.SSLContext | None = None
        self._rpc: subprocess.Popen | None = None
        self._zc = None
        self._zc_info = None
        self._stop = False
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="datas-link")
        self._thread.start()
        self._call(self._startup(), 15)

    # ---- plumbing -----------------------------------------------------------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _call(self, coro, timeout: float = 30):  # noqa: ANN001, ANN202
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _startup(self) -> None:
        self.start_error = ""
        if self.cfg.link_enabled:
            try:
                await self._serve(True)
            except OSError as e:  # port taken: say so in the Devices screen instead of failing
                self.start_error = f"Port {self.cfg.link_port} is in use on this device ({e})."
        self.loop.create_task(self._background())

    def stop(self) -> None:
        self._stop = True
        try:
            self._call(self._serve(False), 5)
        except Exception:  # noqa: BLE001
            pass
        self._stop_rpc()
        self.loop.call_soon_threadsafe(self.loop.stop)

    # ---- peers store ----------------------------------------------------------
    def _peers_path(self) -> Path:
        return link_dir() / "peers.json"

    def _load_peers(self) -> dict[str, dict]:
        try:
            d = json.loads(self._peers_path().read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (ValueError, OSError):
            return {}

    def _save_peers(self) -> None:
        tmp = self._peers_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(self._peers, indent=1), encoding="utf-8")
        tmp.replace(self._peers_path())

    def _add_peer(
        self, pid: str, name: str, cert: str, address: str, kind: str = "device", os: str = ""
    ) -> dict:
        self._peers[pid] = {
            "name": " ".join(str(name).split())[:60] or "device",
            "cert": cert,
            "address": address,
            "added": time.time(),
        }
        if kind == "app":  # a phone or tablet: known by the fingerprint of its secret
            self._peers[pid].update(kind="app", os=str(os)[:20], window=True)
        self._save_peers()
        if self._ctx is not None and cert:
            try:
                self._ctx.load_verify_locations(cadata=cert)
            except ssl.SSLError:
                pass
        self._dirty = True
        return self._peers[pid]

    def is_app(self, pid: str) -> bool:
        return self._peers.get(pid, {}).get("kind") == "app"

    def _computers(self) -> list[str]:
        """Linked devices this one can call (phones only call in)."""
        return [pid for pid in self._peers if not self.is_app(pid)]

    def set_peer(self, pid: str, window: bool | None = None) -> dict:
        if pid not in self._peers:
            raise LinkError("that device is not linked")
        if window is not None and self.is_app(pid):
            self._peers[pid]["window"] = bool(window)
            self._save_peers()
        return self.peer_public(pid)

    def unpair(self, pid: str) -> bool:
        if pid not in self._peers:
            return False
        self._peers.pop(pid)
        self._save_peers()
        self.status.pop(pid, None)
        t = self.tunnels.pop(pid, None)
        if t:
            self.loop.call_soon_threadsafe(t[0].close)
        if self.cfg.provider == f"link:{pid}":
            self.cfg.provider = "local"
            self.cfg.save()
        # The certificate cannot be taken out of a live TLS context; every request also checks
        # the peers list (see _handle), and the context is rebuilt at the next start.
        if self._server is not None:
            self._call(self._serve(False), 5)
            self._call(self._serve(True), 5)
        return True

    # ---- server on/off, pairing -----------------------------------------------
    async def _serve(self, on: bool) -> None:
        if on and self._server is None:
            self._ctx = server_context(
                self.key_p, self.crt_p, [p["cert"] for p in self._peers.values() if p.get("cert")]
            )
            self._server = await asyncio.start_server(
                self._handle, "0.0.0.0", self.cfg.link_port, ssl=self._ctx, limit=4 * BUF
            )
            self.loop.run_in_executor(None, self._advertise, True)
        elif not on and self._server is not None:
            self.loop.run_in_executor(None, self._advertise, False)
            self._server.close()
            self._server = None
            self._ctx = None

    def enable(self, on: bool) -> dict:
        try:
            self._call(self._serve(on), 10)
        except OSError as e:
            raise LinkError(
                f"Could not open port {self.cfg.link_port} on this device ({e}). "
                "Another program may be using it."
            ) from e
        self.cfg.link_enabled = on
        self.cfg.save()
        if not on:
            self.pairing = None
            self._stop_rpc()
        return self.state()

    def begin_pairing(self) -> dict:
        if self._server is None:
            self.enable(True)
        code = new_code()
        self.pairing = {"code": code, "expires": time.time() + CODE_TTL, "tries": 0}
        return self.state()

    def cancel_pairing(self) -> None:
        self.pairing = None

    def pair(self, address: str, code: str) -> dict:
        """Type the other device's address and code here. Returns the new linked device."""
        if len(clean_code(code)) != CODE_LEN:
            raise LinkError(f"the code has {CODE_LEN} letters and digits")
        host, port = split_address(address, self.cfg.link_port)
        try:
            peer = self._call(self._pair(host, port, code), 40)
        except (OSError, asyncio.TimeoutError, TimeoutError, ssl.SSLError) as e:
            raise LinkError(
                f"Could not reach {host}:{port}. Check that Datas is open on the other device, "
                "that it shows the pairing code, and that both are on the same network "
                f"(or that the address is reachable). ({type(e).__name__})"
            ) from e
        if self._server is None:  # so the other device can reach this one too
            try:
                self.enable(True)
            except LinkError:
                pass
        return peer

    async def _pair(self, host: str, port: int, code: str) -> dict:
        ctx = client_context(self.key_p, self.crt_p, None)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx, limit=4 * BUF), 12
        )
        try:
            der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if not der:
                raise LinkError("the other device did not identify itself")
            fp_s = hashlib.sha256(der).hexdigest()
            if fp_s == self.id:
                raise LinkError("that is this same device")
            n_c = os.urandom(16)
            await send(
                writer,
                {
                    "op": "pair",
                    "cert": self.cert,
                    "name": self.name,
                    "nonce": n_c.hex(),
                    "port": self.cfg.link_port,
                },
            )
            r = await asyncio.wait_for(recv(reader, 1 << 20), 15)
            if not r.get("ok"):
                raise LinkError(r.get("error") or "the other device is not waiting for a code")
            n_s = bytes.fromhex(r["nonce"])
            key = await self.loop.run_in_executor(None, derive, code, n_c + n_s)
            await send(writer, {"proof": proof(key, b"client", self.id, fp_s, n_c, n_s).hex()})
            r2 = await asyncio.wait_for(recv(reader, 1 << 20), 15)
            if not r2.get("ok"):
                raise LinkError(r2.get("error") or "wrong or expired code")
            want = proof(key, b"server", fp_s, self.id, n_s, n_c)
            if not hmac.compare_digest(want, bytes.fromhex(r2.get("proof", ""))):
                raise LinkError(
                    "the other device could not prove it knows the code — nothing was linked"
                )
            self._add_peer(
                fp_s, r.get("name") or host, ssl.DER_cert_to_PEM_cert(der), f"{host}:{port}"
            )
            return self.peer_public(fp_s)
        finally:
            writer.close()

    # ---- incoming connections ---------------------------------------------------
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            sslobj = writer.get_extra_info("ssl_object")
            der = sslobj.getpeercert(binary_form=True) if sslobj else None
            pid = hashlib.sha256(der).hexdigest() if der else None
            msg = await asyncio.wait_for(recv(reader, 1 << 20), 20)
            op = msg.get("op")
            if op == "pair":
                await self._op_pair(msg, reader, writer)
                return
            if not pid and isinstance(msg.get("auth"), str):
                # a phone: no certificate; it shows its secret inside the encrypted connection
                try:
                    cand = hashlib.sha256(bytes.fromhex(msg["auth"])).hexdigest()
                except ValueError:
                    cand = ""
                pid = cand if self.is_app(cand) else None
            if not pid or pid not in self._peers:
                await send(writer, {"ok": False, "error": "this device is not linked to that one"})
                return
            self._seen(pid, writer, msg)
            if self.is_app(pid) and op not in ("info", "window"):
                await send(writer, {"ok": False, "error": "a phone cannot ask for that"})
                return
            if op == "info":
                info = await self.loop.run_in_executor(None, self.info)
                await send(writer, {"ok": True, **info})
            elif op == "window":
                await self._op_window(pid, reader, writer)
            elif op == "sync":
                await self._op_sync(msg, reader, writer)
            elif op == "rpc":
                await self._op_rpc(reader, writer)
            elif op == "v1":
                await self._op_v1(msg, writer)
            else:
                await send(writer, {"ok": False, "error": "unknown request"})
        except (
            asyncio.TimeoutError,
            asyncio.IncompleteReadError,
            ConnectionError,
            ssl.SSLError,
            OSError,
            ValueError,
            LinkError,
        ):
            pass
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass

    def _seen(self, pid: str, writer: asyncio.StreamWriter, msg: dict) -> None:
        """A linked device just talked to us: it is online, and this is its address now."""
        st = self.status.setdefault(pid, {})
        st["online"], st["fails"], st["seen"] = True, 0, time.time()
        peername = writer.get_extra_info("peername")
        port = msg.get("port")
        if self.is_app(pid):
            return  # a phone is never called back
        if peername and isinstance(port, int) and 0 < port < 65536:
            addr = f"{peername[0]}:{port}"
            if self._peers[pid].get("address") != addr:
                self._peers[pid]["address"] = addr
                self._save_peers()

    async def _op_pair(self, msg: dict, reader, writer) -> None:  # noqa: ANN001
        p = self.pairing
        if not p or time.time() > p["expires"]:
            self.pairing = None
            await send(
                writer,
                {"ok": False, "error": "that device is not showing a pairing code right now"},
            )
            return
        app = bool(msg.get("app"))
        try:
            if app:
                cert, fp_c = "", str(msg["id"]).lower()
                if len(fp_c) != 64 or len(bytes.fromhex(fp_c)) != 32:
                    raise ValueError("bad id")
            else:
                cert = str(msg["cert"])
                fp_c = fingerprint(cert)
            n_c = bytes.fromhex(msg["nonce"])
        except (KeyError, ValueError):
            await send(writer, {"ok": False, "error": "bad pairing request"})
            return
        n_s = os.urandom(16)
        await send(writer, {"ok": True, "nonce": n_s.hex(), "name": self.name})
        m2 = await asyncio.wait_for(recv(reader, 1 << 20), 30)
        key = await self.loop.run_in_executor(None, derive, p["code"], n_c + n_s)
        want = proof(key, b"client", fp_c, self.id, n_c, n_s)
        try:
            got = bytes.fromhex(m2.get("proof", ""))
        except ValueError:
            got = b""
        if not hmac.compare_digest(want, got):
            p["tries"] += 1
            if p["tries"] >= MAX_TRIES:
                self.pairing = None  # too many wrong codes: start again with a new one
            await send(writer, {"ok": False, "error": "wrong code"})
            return
        self.pairing = None  # a code works once
        peername = writer.get_extra_info("peername") or ("?", 0)
        port = msg.get("port") if isinstance(msg.get("port"), int) else self.cfg.link_port
        if app:
            self._add_peer(fp_c, msg.get("name") or "phone", "", "", "app", msg.get("os") or "")
        else:
            self._add_peer(fp_c, msg.get("name") or peername[0], cert, f"{peername[0]}:{port}")
        st = self.status.setdefault(fp_c, {})
        st["online"], st["fails"], st["seen"] = True, 0, time.time()
        await send(
            writer,
            {"ok": True, "proof": proof(key, b"server", self.id, fp_c, n_s, n_c).hex()},
        )

    # ---- what this device tells its linked devices ---------------------------------
    def info(self) -> dict:
        from datas.recommend.engine import budget_for

        core, cfg = self.core, self.cfg
        b = budget_for(core.spec(), cfg.headroom, cfg.headroom_min_gib)
        running = core.server.running()
        can_share = cfg.link_share_memory and core.runtime_installed() and not running
        ctx = cfg.context
        args = core.server.state.args or []
        for i, a in enumerate(args[:-1]):
            if a in ("-c", "--ctx-size") and str(args[i + 1]).isdigit():
                ctx = int(args[i + 1])
        local_ai = cfg.provider in ("local", "pool")
        return {
            "name": self.name,
            "id": self.id,
            "version": __version__,
            "os": core.spec().os,
            "tag": cfg.llamacpp_tag,
            "backend": b.backend,
            "ram_budget": b.ram_budget if can_share else 0,
            "vram_budget": b.vram_budget if can_share else 0,
            "share_memory": cfg.link_share_memory,
            "engine": core.runtime_installed(),
            "busy": running,
            "ai": {
                "available": local_ai and (running or core.can_wake()),
                "running": running,
                "name": core.model_name(
                    core.server.state.model_id or (cfg.last_run or {}).get("model_id")
                ),
                "context": ctx,
            },
            "sync": cfg.link_sync_chats and not cfg.forget,
            "time": time.time(),
        }

    # ---- op: sync chats ------------------------------------------------------------
    async def _op_sync(self, msg: dict, reader, writer) -> None:  # noqa: ANN001
        if self.cfg.forget or not self.cfg.link_sync_chats:
            await send(writer, {"ok": False, "error": "chat sync is off on that device"})
            return
        theirs = msg.get("manifest") or {}
        chats.apply_tombstones(msg.get("tombstones") or {})
        mine = chats.manifest()
        tomb = chats.tombstones()
        to_send = [i for i, u in mine.items() if u > float(theirs.get(i, 0))]
        want = [
            i for i, u in theirs.items() if float(u) > mine.get(i, 0) and float(u) > tomb.get(i, 0)
        ]
        await send(writer, {"ok": True, "want": want, "tombstones": tomb, "count": len(to_send)})
        for i in to_send:
            d = chats.load_chat(i)
            await send(writer, {"chat": d} if d else {"chat": None})
        head = await asyncio.wait_for(recv(reader), 60)
        for _ in range(int(head.get("count", 0))):
            m = await asyncio.wait_for(recv(reader), 120)
            if m.get("chat"):
                chats.apply_remote_chat(m["chat"])
        await send(writer, {"ok": True})
        self.last_sync = time.time()

    async def _sync_with(self, pid: str) -> None:
        reader, writer = await self._connect(pid)
        try:
            await send(
                writer,
                {
                    "op": "sync",
                    "port": self.cfg.link_port,
                    "manifest": chats.manifest(),
                    "tombstones": chats.tombstones(),
                },
            )
            r = await asyncio.wait_for(recv(reader), 60)
            if not r.get("ok"):
                raise LinkError(r.get("error") or "sync refused")
            chats.apply_tombstones(r.get("tombstones") or {})
            for _ in range(int(r.get("count", 0))):
                m = await asyncio.wait_for(recv(reader), 120)
                if m.get("chat"):
                    chats.apply_remote_chat(m["chat"])
            mine = [chats.load_chat(i) for i in r.get("want") or []]
            mine = [c for c in mine if c]
            await send(writer, {"count": len(mine)})
            for c in mine:
                await send(writer, {"chat": c})
            await asyncio.wait_for(recv(reader), 60)
            self.last_sync = time.time()
        finally:
            writer.close()

    def chats_changed(self) -> None:
        self._dirty = True

    def sync_now(self) -> dict:
        """Sync with every linked device that is online. Returns what happened."""
        if self.cfg.forget:
            raise LinkError("In Forget mode nothing is saved, so there is nothing to sync.")
        return self._call(self._sync_all(), 180)

    async def _sync_all(self) -> dict:
        done, errors = [], []
        for pid in self._computers():
            if not self.status.get(pid, {}).get("online"):
                continue
            try:
                await self._sync_with(pid)
                done.append(self._peers[pid]["name"])
            except (
                LinkError,
                OSError,
                asyncio.TimeoutError,
                ssl.SSLError,
                asyncio.IncompleteReadError,
            ) as e:
                errors.append(f"{self._peers[pid]['name']}: {e}")
        self._dirty = bool(errors)
        self.sync_error = "; ".join(errors)
        return {"synced_with": done, "errors": errors}

    # ---- op: memory sharing (llama.cpp RPC through the link) -------------------------
    def _stop_rpc(self) -> None:
        if self._rpc and self._rpc.poll() is None:
            self._rpc.terminate()
            try:
                self._rpc.wait(5)
            except Exception:  # noqa: BLE001
                self._rpc.kill()
        self._rpc = None

    def _ensure_rpc(self) -> int:
        """Start llama.cpp's worker bound to this device only (127.0.0.1). Returns its port."""
        from datas.recommend.engine import budget_for
        from datas.runtime import llamacpp

        port = self.cfg.rpc_port
        if self._rpc and self._rpc.poll() is None:
            return port
        exe = llamacpp.binary(self.cfg, "rpc-server")
        b = budget_for(self.core.spec(), self.cfg.headroom, self.cfg.headroom_min_gib)
        env = os.environ.copy()
        if sys.platform.startswith("linux"):
            env["LD_LIBRARY_PATH"] = str(exe.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        elif sys.platform == "darwin":
            env["DYLD_LIBRARY_PATH"] = (
                str(exe.parent) + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
            )
        self._rpc = subprocess.Popen(
            [str(exe), "-H", "127.0.0.1", "-p", str(port), "-t", str(b.threads), "-c"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(exe.parent),
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._rpc.poll() is not None:
                raise LinkError("the engine's worker could not start on that device")
            with socket.socket() as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return port
            time.sleep(0.2)
        raise LinkError("the engine's worker did not start in time")

    async def _op_rpc(self, reader, writer) -> None:  # noqa: ANN001
        if not self.cfg.link_share_memory:
            await send(writer, {"ok": False, "error": "that device is not sharing its memory"})
            return
        if self.core.server.running():
            await send(writer, {"ok": False, "error": "that device is busy running its own AI"})
            return
        try:
            port = await self.loop.run_in_executor(None, self._ensure_rpc)
            r2, w2 = await asyncio.open_connection("127.0.0.1", port, limit=4 * BUF)
        except Exception as e:  # noqa: BLE001 - engine missing, port busy…
            await send(writer, {"ok": False, "error": f"memory sharing is not ready there: {e}"})
            return
        await send(writer, {"ok": True})
        await splice(reader, writer, r2, w2)

    # ---- op: this device's Datas window, for a linked phone -------------------------
    async def _op_window(self, pid: str, reader, writer) -> None:  # noqa: ANN001
        """Join the encrypted connection to the local service, so the phone's app can show
        this device's Datas. The service is told which of its connections come this way
        (``core.remote_clients``) and refuses, on those, what should only be done at the
        device itself (see ``remote_refusal`` in datas/server/app.py)."""
        if not self._peers[pid].get("window"):
            await send(
                writer,
                {"ok": False, "error": "that device did not allow this one to open its Datas"},
            )
            return
        try:
            r2, w2 = await asyncio.open_connection("127.0.0.1", self.core.http_port, limit=4 * BUF)
        except OSError as e:
            await send(
                writer, {"ok": False, "error": f"Datas is not answering on that device ({e})"}
            )
            return
        me = w2.get_extra_info("sockname")[:2]
        self.core.remote_clients[me] = pid
        try:
            await send(writer, {"ok": True})
            await splice(reader, writer, r2, w2)
        finally:
            self.core.remote_clients.pop(me, None)
            self.status.setdefault(pid, {})["seen"] = time.time()

    async def _ensure_tunnel(self, pid: str) -> int:
        """A door on this device (127.0.0.1) that leads, encrypted, to the worker on ``pid``."""
        if pid in self.tunnels:
            return self.tunnels[pid][1]

        async def on_conn(lr: asyncio.StreamReader, lw: asyncio.StreamWriter) -> None:
            try:
                r, w = await self._connect(pid)
                await send(w, {"op": "rpc", "port": self.cfg.link_port})
                head = await asyncio.wait_for(recv(r, 1 << 20), 30)
                if not head.get("ok"):
                    raise LinkError(head.get("error") or "refused")
            except Exception:  # noqa: BLE001
                self._fail(pid)
                lw.close()
                return
            await splice(lr, lw, r, w)

        srv = await asyncio.start_server(on_conn, "127.0.0.1", 0, limit=4 * BUF)
        port = srv.sockets[0].getsockname()[1]
        self.tunnels[pid] = (srv, port)
        return port

    def pool_nodes(self, refresh: bool = False) -> list:
        """Linked devices that are online and offering memory, as endpoints llama.cpp can use."""
        from datas.pool.discovery import Node

        if refresh:
            self.refresh()
        out = []
        for pid, p in self._peers.items():
            st = self.status.get(pid, {})
            info = st.get("info") or {}
            if not st.get("online") or not (info.get("ram_budget") or info.get("vram_budget")):
                continue
            port = self._call(self._ensure_tunnel(pid), 10)
            out.append(
                Node(
                    host=p["name"],
                    ip="127.0.0.1",
                    port=port,
                    tag=info.get("tag", ""),
                    backend=info.get("backend", ""),
                    ram_budget=int(info.get("ram_budget", 0)),
                    vram_budget=int(info.get("vram_budget", 0)),
                    datas_version=info.get("version", ""),
                )
            )
        return out

    def tunnel_owner(self, endpoint: str) -> str | None:
        for pid, (_, port) in self.tunnels.items():
            if endpoint == f"127.0.0.1:{port}":
                return pid
        return None

    # ---- op: use the AI running on a linked device ----------------------------------
    async def _op_v1(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        import httpx

        from datas.providers import active_provider

        core = self.core
        path = str(msg.get("path", "")).strip("/")
        if path not in V1_PATHS:
            await send(writer, {"ok": False, "error": "not available over the link"})
            return
        if self.cfg.provider not in ("local", "pool"):
            await send(
                writer, {"ok": False, "error": "that device is not running an AI of its own"}
            )
            return
        if not core.server.running() and core.can_wake():
            try:
                await self.loop.run_in_executor(None, core.wake)
            except Exception as e:  # noqa: BLE001
                await send(
                    writer, {"ok": False, "error": f"the AI on that device could not start: {e}"}
                )
                return
        if not core.server.running():
            await send(writer, {"ok": False, "error": "no AI is running on that device"})
            return
        prov = active_provider(self.cfg, True, core.server.state.rpc)
        body = msg.get("body")
        if isinstance(body, dict):
            body["model"] = prov.model or "default"
        core.touch()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(600, connect=30), trust_env=False
        ) as client:
            try:
                req = client.build_request(
                    "POST" if body is not None else "GET",
                    f"{prov.base_url}/{path}",
                    json=body,
                    headers=prov.headers(),
                )
                resp = await client.send(req, stream=True)
            except httpx.HTTPError as e:
                await send(
                    writer, {"ok": False, "error": f"the AI on that device did not answer: {e}"}
                )
                return
            try:
                await send(
                    writer,
                    {
                        "ok": True,
                        "status": resp.status_code,
                        "content_type": resp.headers.get("content-type", "application/json"),
                    },
                )
                async for chunk in resp.aiter_raw():
                    core.touch()
                    writer.write(chunk)
                    await writer.drain()
            finally:
                await resp.aclose()

    async def open_v1(self, pid: str, path: str, body: dict | None):  # noqa: ANN201
        """For the local API (runs in the caller's event loop): returns (reader, writer, head);
        the reader then yields the other device's answer as it is produced."""
        reader, writer = await self._connect(pid)
        try:
            await send(writer, {"op": "v1", "port": self.cfg.link_port, "path": path, "body": body})
            head = await asyncio.wait_for(recv(reader, 1 << 20), 120)
        except Exception:
            writer.close()
            raise
        if not head.get("ok"):
            writer.close()
            raise LinkError(head.get("error") or "the other device refused")
        return reader, writer, head

    # ---- outgoing connections, presence ----------------------------------------------
    async def _connect(self, pid: str):  # noqa: ANN202
        p = self._peers.get(pid)
        if not p:
            raise LinkError("that device is not linked")
        host, port = split_address(p["address"], self.cfg.link_port)
        ctx = client_context(self.key_p, self.crt_p, p["cert"])
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx, limit=4 * BUF), 6
        )
        der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
        if not der or hashlib.sha256(der).hexdigest() != pid:  # belt and braces on top of pinning
            writer.close()
            raise LinkError("the device at that address is not the one that was linked")
        return reader, writer

    def _fail(self, pid: str) -> None:
        st = self.status.setdefault(pid, {})
        st["fails"] = st.get("fails", 0) + 1
        if st["fails"] >= 2:
            st["online"] = False

    async def _check(self, pid: str) -> None:
        st = self.status.setdefault(pid, {})
        try:
            reader, writer = await self._connect(pid)
            try:
                await send(writer, {"op": "info", "port": self.cfg.link_port})
                info = await asyncio.wait_for(recv(reader, 1 << 20), 8)
            finally:
                writer.close()
            if not info.get("ok"):
                raise LinkError(info.get("error") or "refused")
            st.update(online=True, fails=0, info=info, checked=time.time(), error="")
            if info.get("name") and info["name"] != self._peers[pid]["name"]:
                self._peers[pid]["name"] = str(info["name"])[:60]
                self._save_peers()
        except (
            LinkError,
            OSError,
            asyncio.TimeoutError,
            ssl.SSLError,
            asyncio.IncompleteReadError,
            ValueError,
        ) as e:
            st["error"] = str(e) or type(e).__name__
            st["checked"] = time.time()
            self._fail(pid)

    def refresh(self) -> None:
        """Ask every linked device how it is, now."""
        self._call(self._refresh(), 30)

    async def _refresh(self) -> None:
        for pid in self._peers:  # a phone counts as present for a minute after it last called
            if self.is_app(pid):
                st = self.status.setdefault(pid, {})
                st["online"] = time.time() - st.get("seen", 0) < 60
        if self._computers():
            await asyncio.gather(*(self._check(pid) for pid in self._computers()))

    async def _background(self) -> None:
        tick = 0
        while not self._stop:
            try:
                pooled = bool(self.core.server.state.rpc) and self.core.server.running()
                await asyncio.sleep(8 if pooled else 20)
                tick += 1
                if not self._peers:
                    continue
                await self._refresh()
                if tick % 6 == 0:
                    await self.loop.run_in_executor(None, self._rediscover)
                # a device this AI is spread over went away → carry on with what fits here
                if pooled:
                    lost = [
                        self._peers[pid]["name"]
                        for pid in {self.tunnel_owner(e) for e in self.core.server.state.rpc}
                        if pid and pid in self._peers and not self.status.get(pid, {}).get("online")
                    ]
                    if lost:
                        await self.loop.run_in_executor(
                            None, self.core.fallback_local, ", ".join(lost)
                        )
                # chats: when something changed, and every couple of minutes anyway
                if (
                    self.cfg.link_sync_chats
                    and not self.cfg.forget
                    and (self._dirty or time.time() - self.last_sync > 120)
                    and any(self.status.get(p, {}).get("online") for p in self._computers())
                ):
                    await self._sync_all()
            except Exception:  # noqa: BLE001 - the loop must outlive any single failure
                await asyncio.sleep(5)

    # ---- finding devices on the local network (names only; pairing still needs the code) ---
    def _advertise(self, on: bool) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf

            if on and self._zc is None:
                addrs = local_addresses()
                if not addrs:
                    return
                self._zc = Zeroconf()
                self._zc_info = ServiceInfo(
                    MDNS_TYPE,
                    f"datas-{self.id[:12]}.{MDNS_TYPE}",
                    addresses=[socket.inet_aton(a) for a in addrs[:1]],
                    port=self.cfg.link_port,
                    properties={"name": self.name, "id": self.id[:16]},
                )
                self._zc.register_service(self._zc_info)
            elif not on and self._zc is not None:
                try:
                    self._zc.unregister_service(self._zc_info)
                finally:
                    self._zc.close()
                    self._zc = None
        except Exception:  # noqa: BLE001 - discovery is a convenience, never a requirement
            self._zc = None

    def nearby(self, seconds: float = 2.5) -> list[dict]:
        """Devices with Datas linking switched on, seen on this network."""
        try:
            from zeroconf import ServiceBrowser, Zeroconf
        except Exception:  # noqa: BLE001
            return []
        found: dict[str, dict] = {}

        class L:
            def add_service(self, zc, type_, name):  # noqa: ANN001
                info = zc.get_service_info(type_, name, timeout=1500)
                if not info or not info.addresses:
                    return
                props = {
                    (k.decode() if isinstance(k, bytes) else k): (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in (info.properties or {}).items()
                }
                found[name] = {
                    "name": props.get("name", name.split(".")[0]),
                    "id": props.get("id", ""),
                    "address": f"{socket.inet_ntoa(info.addresses[0])}:{info.port}",
                }

            update_service = add_service

            def remove_service(self, zc, type_, name):  # noqa: ANN001
                found.pop(name, None)

        try:
            zc = Zeroconf()
            ServiceBrowser(zc, MDNS_TYPE, L())
            time.sleep(seconds)
            zc.close()
        except Exception:  # noqa: BLE001
            return []
        known = {pid[:16] for pid in self._peers}
        return [d | {"linked": d["id"] in known} for d in found.values() if d["id"] != self.id[:16]]

    def _rediscover(self) -> None:
        """A linked device that changed address (new Wi-Fi lease) is found again by its id."""
        offline = [pid for pid in self._computers() if not self.status.get(pid, {}).get("online")]
        if not offline or self._server is None:
            return
        for d in self.nearby(1.5):
            for pid in offline:
                if (
                    d["id"]
                    and pid.startswith(d["id"])
                    and self._peers[pid]["address"] != d["address"]
                ):
                    self._peers[pid]["address"] = d["address"]
                    self._save_peers()

    # ---- for the window -------------------------------------------------------------
    def peer_public(self, pid: str) -> dict:
        p = self._peers[pid]
        st = self.status.get(pid, {})
        info = st.get("info") or {}
        mem = (info.get("ram_budget", 0) + info.get("vram_budget", 0)) / 2**30
        app = p.get("kind") == "app"
        return {
            "id": pid,
            "short_id": short_id(pid),
            "name": p["name"],
            "kind": "app" if app else "device",
            "window": bool(p.get("window")) if app else False,
            "seen": st.get("seen"),
            "address": p["address"],
            "added": p.get("added"),
            "online": (time.time() - st.get("seen", 0) < 60) if app else bool(st.get("online")),
            "error": st.get("error", "") if not st.get("online") and not app else "",
            "os": p.get("os", "") if app else info.get("os", ""),
            "version": info.get("version", ""),
            "memory_gib": round(mem, 1),
            "shares_memory": bool(info.get("share_memory")),
            "busy": bool(info.get("busy")),
            "engine": bool(info.get("engine")),
            "tag": info.get("tag", ""),
            "tag_matches": not info.get("tag") or info.get("tag") == self.cfg.llamacpp_tag,
            "ai": info.get("ai") or {},
            "sync": bool(info.get("sync")),
            "in_use": self.cfg.provider == f"link:{pid}",
        }

    def state(self) -> dict:
        p = self.pairing
        if p and time.time() > p["expires"]:
            p = self.pairing = None
        addrs = [f"{a}:{self.cfg.link_port}" for a in local_addresses()]
        return {
            "enabled": self._server is not None,
            "device": {"name": self.name, "id": self.id, "short_id": short_id(self.id)},
            "port": self.cfg.link_port,
            "addresses": addrs,
            "pairing": (
                {
                    "code": pretty_code(p["code"]),
                    "expires_in": int(p["expires"] - time.time()),
                    "addresses": addrs,
                }
                if p
                else None
            ),
            "peers": [self.peer_public(pid) for pid in self._peers],
            "share_memory": self.cfg.link_share_memory,
            "sync_chats": self.cfg.link_sync_chats,
            "forget": self.cfg.forget,
            "last_sync": self.last_sync or None,
            "sync_error": self.sync_error,
            "error": getattr(self, "start_error", ""),
        }

    def rename(self, name: str) -> None:
        name = " ".join(name.split())[:40]
        if name:
            self.name = name
            self.cfg.device_name = name
            self.cfg.save()
