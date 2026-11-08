from __future__ import annotations

import socket
import time
from dataclasses import asdict, dataclass

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

SERVICE = "_datas-rpc._tcp.local."
GiB = 2**30


@dataclass
class Node:
    host: str
    ip: str
    port: int
    tag: str = ""
    backend: str = ""
    ram_budget: int = 0
    vram_budget: int = 0
    datas_version: str = ""

    @property
    def endpoint(self) -> str:
        return f"{self.ip}:{self.port}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["endpoint"] = self.endpoint
        d["ram_budget_gib"] = round(self.ram_budget / GiB, 1)
        d["vram_budget_gib"] = round(self.vram_budget / GiB, 1)
        return d


def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; picks the default route's interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _txt(d: dict) -> dict[str, str]:
    return {k: str(v) for k, v in d.items()}


def advertise(
    port: int, tag: str, backend: str, ram_budget: int, vram_budget: int, version: str
) -> tuple[Zeroconf, ServiceInfo]:
    """Register this worker on the LAN. Caller must unregister/close on exit."""
    host = socket.gethostname().split(".")[0]
    ip = _local_ip()
    info = ServiceInfo(
        SERVICE,
        f"{host}.{SERVICE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties=_txt(
            {
                "tag": tag,
                "backend": backend,
                "ram_budget": ram_budget,
                "vram_budget": vram_budget,
                "datas": version,
                "host": host,
            }
        ),
        server=f"{host}.local.",
    )
    zc = Zeroconf()
    zc.register_service(info)
    return zc, info


class _Listener:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}

    def _add(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=1500)
        if not info or not info.addresses:
            return
        props = {
            k.decode() if isinstance(k, bytes) else k: (v.decode() if isinstance(v, bytes) else v)
            for k, v in (info.properties or {}).items()
        }
        ip = socket.inet_ntoa(info.addresses[0])
        self.nodes[name] = Node(
            host=props.get("host", name.split(".")[0]),
            ip=ip,
            port=info.port,
            tag=props.get("tag", ""),
            backend=props.get("backend", ""),
            ram_budget=int(props.get("ram_budget", 0) or 0),
            vram_budget=int(props.get("vram_budget", 0) or 0),
            datas_version=props.get("datas", ""),
        )

    add_service = _add
    update_service = _add

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.nodes.pop(name, None)


def discover(seconds: float = 3.0, exclude_self: bool = True) -> list[Node]:
    zc = Zeroconf()
    listener = _Listener()
    ServiceBrowser(zc, SERVICE, listener)
    try:
        time.sleep(seconds)
    finally:
        zc.close()
    nodes = list(listener.nodes.values())
    if exclude_self:
        me = _local_ip()
        nodes = [n for n in nodes if n.ip != me]
    return sorted(nodes, key=lambda n: n.host)


def parse_manual(spec: str) -> list[Node]:
    """'192.168.1.20:50052,desk.local:50052' → Nodes (no metadata)."""
    out: list[Node] = []
    for item in [s.strip() for s in spec.split(",") if s.strip()]:
        host, _, port = item.rpartition(":")
        if not host:
            host, port = item, "50052"
        try:
            ip = socket.gethostbyname(host)
        except OSError:
            ip = host
        out.append(Node(host=host, ip=ip, port=int(port)))
    return out
