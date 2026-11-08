"""Providers: where tokens come from.

Everything above this layer (chat UI, agents, the /v1 proxy) talks to *one* interface —
an OpenAI-compatible ``/v1/chat/completions`` endpoint — so switching between a local
model, a pooled cluster and a paid API is a config change, not a code path.

    local  → llama-server on this machine (started by Datas)
    pool   → llama-server on this machine with --rpc workers (memory pooled)
    remote → any OpenAI-compatible HTTP API with your key (OpenAI, Groq, Mistral,
             OpenRouter, Together, a friend's Datas node, Ollama, LM Studio, …)

Keys live in the local config file only. Datas never sends them anywhere except the
base_url you configured.
"""

from __future__ import annotations

from dataclasses import dataclass

from datas.config import Config, RemoteProviderConfig

# Base URLs of popular OpenAI-compatible endpoints, offered as presets in the UI.
# The user supplies the key and picks the model; nothing here is pre-filled.
PRESETS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic (openai-compatible)": "https://api.anthropic.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "ollama (local)": "http://127.0.0.1:11434/v1",
    "lm studio (local)": "http://127.0.0.1:1234/v1",
    "another datas node": "http://<host>:8421/v1",
}


@dataclass
class Provider:
    name: str
    kind: str  # local | pool | remote
    base_url: str
    api_key: str = ""
    model: str = ""
    available: bool = True
    detail: str = ""

    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
            # Anthropic's compatibility endpoint also accepts the key as x-api-key
            if "anthropic.com" in self.base_url:
                h["x-api-key"] = self.api_key
                h["anthropic-version"] = "2023-06-01"
        return h

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "model": self.model,
            "has_key": bool(self.api_key),
            "available": self.available,
            "detail": self.detail,
        }


def local_provider(
    cfg: Config, running: bool, model_id: str = "", rpc: list[str] | None = None
) -> Provider:
    kind = "pool" if rpc else "local"
    return Provider(
        name=kind,
        kind=kind,
        base_url=f"http://127.0.0.1:{cfg.llama_port}/v1",
        model=model_id or cfg.model_id,
        available=running,
        detail=("running" if running else "stopped") + (f", {len(rpc)} worker(s)" if rpc else ""),
    )


def remote_provider(r: RemoteProviderConfig) -> Provider:
    return Provider(
        name=r.name,
        kind="remote",
        base_url=r.base_url.rstrip("/"),
        api_key=r.api_key,
        model=r.model,
        available=bool(r.base_url),
        detail="api key set" if r.api_key else "no key",
    )


def all_providers(cfg: Config, running: bool, rpc: list[str] | None = None) -> list[Provider]:
    out = [local_provider(cfg, running, rpc=rpc)]
    out += [remote_provider(r) for r in cfg.remotes]
    return out


def active_provider(cfg: Config, running: bool, rpc: list[str] | None = None) -> Provider:
    if cfg.provider in ("local", "pool"):
        return local_provider(cfg, running, rpc=rpc)
    r = cfg.remote(cfg.provider)
    if r is None:
        return local_provider(cfg, running, rpc=rpc)
    return remote_provider(r)


def set_remote(
    cfg: Config, name: str, base_url: str, api_key: str = "", model: str = ""
) -> RemoteProviderConfig:
    existing = cfg.remote(name)
    if existing:
        existing.base_url = base_url or existing.base_url
        if api_key:
            existing.api_key = api_key
        if model:
            existing.model = model
        cfg.save()
        return existing
    r = RemoteProviderConfig(name=name, base_url=base_url, api_key=api_key, model=model)
    cfg.remotes.append(r)
    cfg.save()
    return r


def remove_remote(cfg: Config, name: str) -> bool:
    before = len(cfg.remotes)
    cfg.remotes = [r for r in cfg.remotes if r.name != name]
    if cfg.provider == name:
        cfg.provider = "local"
    cfg.save()
    return len(cfg.remotes) < before
