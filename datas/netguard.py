"""Where the AI may go on the network: the public internet only.

When the user switches the internet on, the AI can search and open web pages. A page it reads
could contain text such as "now open http://192.168.1.1/…" (the user's router) or
"http://127.0.0.1:8420/api/…" (Datas itself). Obeying that would let a stranger's web page read
private things through the AI — the attack is called Server-Side Request Forgery (SSRF).

So every address the AI asks for is checked before the request (the name must resolve only to
public addresses), every redirect is checked the same way, and the address actually connected
to is checked again before any content is handed to the AI. The user can lift this for their
own network in Settings (``allow_local_fetch``) — for instance to let the AI read a page on a
home server.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

UA = "Mozilla/5.0 (Datas.ar local assistant)"
MAX_REDIRECTS = 5
MAX_BYTES = 3_000_000


class Blocked(ValueError):
    """The address is not on the public internet (or is not a web address at all)."""


@dataclass
class Fetched:
    url: str
    status: int
    content_type: str
    body: bytes
    truncated: bool = False

    @property
    def text(self) -> str:
        enc = "utf-8"
        if "charset=" in self.content_type:
            enc = self.content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(enc, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def is_public_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_global and not a.is_multicast


def _proxied() -> bool:
    """With a system proxy the connection goes to the proxy, which does its own name lookup."""
    return any(
        os.environ.get(k) for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
    )


def check_url(url: str, allow_local: bool = False) -> None:
    """Raises ``Blocked`` unless ``url`` is an http(s) address that resolves only to public IPs."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise Blocked("only web addresses (http or https) can be opened")
    host = parts.hostname
    if not host:
        raise Blocked("the address has no site name")
    if allow_local:
        return
    try:
        ipaddress.ip_address(host)
        addrs = [host]
    except ValueError:
        if _proxied():
            if host == "localhost" or host.endswith((".local", ".lan", ".internal", ".home")):
                raise Blocked("that address is inside your own network") from None
            return  # the proxy resolves the name; we cannot see where it leads
        try:
            infos = socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
        except OSError as e:
            raise Blocked(f"the site name could not be found ({e})") from e
        addrs = [i[4][0] for i in infos]
    if not addrs or not all(is_public_ip(a) for a in addrs):
        raise Blocked(
            "that address is inside your own network or this device, not on the public internet"
        )


def _peer_ok(resp: httpx.Response) -> bool:
    if _proxied():
        return True
    try:
        addr = resp.extensions["network_stream"].get_extra_info("server_addr")
    except Exception:  # noqa: BLE001 - transport without that detail: the pre-check stands
        return True
    return not addr or is_public_ip(str(addr[0]))


def _headers(extra: dict | None) -> dict:
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,text/plain,*/*;q=0.8"}
    if extra:
        h.update(extra)
    return h


async def aget(
    client: httpx.AsyncClient,
    url: str,
    allow_local: bool = False,
    params: dict | None = None,
    headers: dict | None = None,
    max_bytes: int = MAX_BYTES,
) -> Fetched:
    """GET for the AI's web tools: checks the address, every redirect and the real peer."""
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url, allow_local)
        async with client.stream(
            "GET", url, params=params, headers=_headers(headers), follow_redirects=False
        ) as r:
            params = None
            if not allow_local and not _peer_ok(r):
                raise Blocked("the site answered from an address inside your own network")
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(str(r.url), r.headers["location"])
                continue
            body = bytearray()
            truncated = False
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    truncated = True
                    break
            return Fetched(
                str(r.url),
                r.status_code,
                r.headers.get("content-type", ""),
                bytes(body[:max_bytes]),
                truncated,
            )
    raise Blocked("too many redirects")


def get(
    url: str,
    allow_local: bool = False,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
    max_bytes: int = MAX_BYTES,
) -> Fetched:
    """The same for code that is not async (the agent's tools)."""
    with httpx.Client(timeout=timeout) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url, allow_local)
            with client.stream(
                "GET", url, params=params, headers=_headers(headers), follow_redirects=False
            ) as r:
                params = None
                if not allow_local and not _peer_ok(r):
                    raise Blocked("the site answered from an address inside your own network")
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    url = urljoin(str(r.url), r.headers["location"])
                    continue
                body = bytearray()
                truncated = False
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        truncated = True
                        break
                return Fetched(
                    str(r.url),
                    r.status_code,
                    r.headers.get("content-type", ""),
                    bytes(body[:max_bytes]),
                    truncated,
                )
    raise Blocked("too many redirects")
