"""Paths and persistent configuration.

Everything Datas writes lives under the platform data dir (``~/.local/share/datas`` on
Linux, ``~/Library/Application Support/datas`` on macOS, ``%LOCALAPPDATA%\\datas`` on
Windows). Override with ``DATAS_HOME``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

APP = "datas"


def home() -> Path:
    override = os.environ.get("DATAS_HOME")
    base = Path(override).expanduser() if override else Path(user_data_dir(APP, appauthor=False))
    base.mkdir(parents=True, exist_ok=True)
    return base


def models_dir() -> Path:
    p = home() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runtime_dir() -> Path:
    p = home() / "llamacpp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = home() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def agent_workspace() -> Path:
    p = home() / "agent-workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


CONFIG_PATH_NAME = "config.json"


@dataclass
class RemoteProviderConfig:
    name: str
    base_url: str
    api_key: str = ""
    model: str = ""


@dataclass
class Config:
    # Fraction of RAM/VRAM to keep free for the OS and your other apps. 0.25 = keep 25%.
    headroom: float = 0.25
    # Minimum absolute headroom in GiB regardless of fraction (small devices need this).
    headroom_min_gib: float = 2.0
    # Default context window to budget for.
    context: int = 8192
    # llama.cpp release tag pinned for this install (pool nodes must match).
    llamacpp_tag: str = ""
    # Backend override: "", "cpu", "cuda", "rocm", "vulkan", "metal"
    backend: str = ""
    # Active provider: "local" | "pool" | name of a remote provider
    provider: str = "local"
    # Currently selected catalog model id and quant (set after install/run)
    model_id: str = ""
    quant: str = ""
    # Local server ports
    ui_port: int = 8420
    llama_port: int = 8421
    rpc_port: int = 50052
    # Manual pool workers ("host:port,host:port") in addition to mDNS discovery
    pool_nodes: str = ""
    # UI language: "en" | "es"
    lang: str = "en"
    # ---- privacy switches (set during the first-run welcome; changeable any time) ----
    # "remember": chats and a short notes file are kept on this device so the AI can learn
    #             your preferences over time.
    # "forget":   nothing is written to disk — no chats, no notes, no engine logs.
    memory_mode: str = ""  # "" = not chosen yet
    keep_logs: bool = True  # technical logs (never your messages); forced off in "forget"
    internet_default: bool = False  # the AI may browse only when you switch it on for a session
    onboarded: bool = False
    # Last use-case / resource-mode choices (so the Home screen remembers them)
    use_cases: str = "text"
    resource_mode: str = "balanced"
    # Pool: offer this device to my other devices (runs a worker in the background)
    pool_offer: bool = False

    @property
    def forget(self) -> bool:
        return self.memory_mode == "forget"

    # Remote OpenAI-compatible providers (API keys live here, on disk, never uploaded)
    remotes: list[RemoteProviderConfig] = field(default_factory=list)
    # Telemetry: none. This flag exists so it can never be flipped on silently.
    telemetry: bool = False

    @classmethod
    def load(cls) -> Config:
        p = home() / CONFIG_PATH_NAME
        if not p.exists():
            return cls()
        data = json.loads(p.read_text())
        remotes = [RemoteProviderConfig(**r) for r in data.pop("remotes", [])]
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        cfg = cls(**known)
        cfg.remotes = remotes
        return cfg

    def save(self) -> Path:
        p = home() / CONFIG_PATH_NAME
        p.write_text(json.dumps(asdict(self), indent=2))
        return p

    def remote(self, name: str) -> RemoteProviderConfig | None:
        for r in self.remotes:
            if r.name == name:
                return r
        return None
