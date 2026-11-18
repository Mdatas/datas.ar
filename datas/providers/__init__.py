"""Providers: where the AI's words come from.

Everything above this layer (chat, agent, the /v1 endpoint other apps use) talks to *one*
interface — an OpenAI-compatible ``/v1/chat/completions`` endpoint — so using the AI on this
device or the AI on another of the user's own devices is a setting, not a code path.

    local  → llama-server on this machine (started by Datas)
    linked → the AI running on another of the user's devices, through the encrypted link
             (datas.link); the request goes to /link/<device>/v1 on this machine, which
             forwards it over mutual TLS

There is no third kind. Paid online AIs (an API key for a company's service) were removed in
0.9: Datas runs on your own devices, and a chat sent to a company's service would leave them.
"""

from __future__ import annotations

from dataclasses import dataclass

from datas.config import Config

HTTP_PORT: int | None = None  # set by the server when it starts (it may not be the default)


@dataclass
class Provider:
    name: str
    kind: str  # local | linked
    base_url: str
    model: str = ""
    available: bool = True
    detail: str = ""

    def headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "model": self.model,
            "available": self.available,
            "detail": self.detail,
        }


def local_provider(cfg: Config, running: bool, model_id: str = "") -> Provider:
    return Provider(
        name="local",
        kind="local",
        base_url=f"http://127.0.0.1:{cfg.llama_port}/v1",
        model=model_id or cfg.model_id,
        available=running,
        detail="running" if running else "stopped",
    )


def linked_provider(cfg: Config, device_id: str) -> Provider:
    return Provider(
        name=f"link:{device_id}",
        kind="linked",
        base_url=f"http://127.0.0.1:{HTTP_PORT or cfg.ui_port}/link/{device_id}/v1",
        model="datas",
        detail="the AI on a linked device",
    )


def all_providers(cfg: Config, running: bool) -> list[Provider]:
    return [local_provider(cfg, running)]


def active_provider(cfg: Config, running: bool) -> Provider:
    if cfg.provider.startswith("link:"):
        return linked_provider(cfg, cfg.provider[5:])
    # "local", and anything older versions saved ("pool", the name of a paid service)
    return local_provider(cfg, running)
