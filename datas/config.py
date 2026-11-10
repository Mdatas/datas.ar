"""Paths and persistent configuration.

Everything Datas writes lives under the platform data dir (``~/.local/share/datas`` on
Linux, ``~/Library/Application Support/datas`` on macOS, ``%LOCALAPPDATA%\\datas`` on
Windows). Override with ``DATAS_HOME``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

APP = "datas"


def home() -> Path:
    override = os.environ.get("DATAS_HOME")
    base = Path(override).expanduser() if override else Path(user_data_dir(APP, appauthor=False))
    base.mkdir(parents=True, exist_ok=True)
    return base


_write_locks: dict[str, threading.Lock] = {}
_write_guard = threading.Lock()


def write_text_safely(path: Path, text: str, private: bool = False, backup: bool = False) -> Path:
    """Save a file so that it is never left half-written and two savers at once never trip
    over each other: the text goes to a temporary file of its own, which then takes the place
    of the old one in a single step.

    ``private``  readable by this user only (settings that hold keys or passwords)
    ``backup``   keep the previous copy beside it as ``<name>.bak``
    """
    with _write_guard:
        lock = _write_locks.setdefault(str(path), threading.Lock())
    with lock:
        tmp = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        if private:
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
        if backup and path.exists():
            try:
                path.replace(path.with_name(path.name + ".bak"))
            except OSError:
                pass
        for attempt in range(6):
            try:
                tmp.replace(path)
                break
            except PermissionError:
                # Windows: another program (an antivirus, a backup) has the file open for a moment
                if attempt == 5:
                    tmp.unlink(missing_ok=True)
                    raise
                time.sleep(0.05 * (attempt + 1))
            except OSError:
                tmp.unlink(missing_ok=True)
                raise
    return path


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


def rotate_log(path: Path, max_bytes: int = 5 * 2**20) -> None:
    """Keep logs small: past ``max_bytes`` the file becomes ``<name>.1`` (one old copy kept)."""
    try:
        if path.exists() and path.stat().st_size > max_bytes:
            old = path.with_name(path.name + ".1")
            old.unlink(missing_ok=True)
            path.replace(old)
    except OSError:
        pass


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
    # Version that last ran, to greet the user once after an upgrade or reinstall
    last_version: str = ""
    # Voice: hearing model ("auto" picks by device: tiny/base/small/large-v3-turbo-q5_0),
    # speaking voice ("auto" = language default), read answers aloud by default
    voice_stt_model: str = "auto"
    voice_tts_voice: str = "auto"
    voice_speak_answers: bool = False
    # Images (stable-diffusion.cpp): engine build ("auto" = Vulkan on any GPU, Metal on Mac, else CPU;
    # or cuda / rocm / vulkan / cpu) and the port of its local server
    image_backend: str = "auto"
    sd_port: int = 8422
    # stable-diffusion.cpp build in use ("" = the one this version was tested with)
    sd_tag: str = ""
    # Look of the window: "auto" follows the computer's light/dark setting, or "day" / "night"
    theme: str = "auto"
    # Put the AI to sleep after this many quiet minutes to give the memory back (0 = never);
    # it wakes by itself on the next message.
    idle_sleep_min: int = 30
    # How the AI was last started (model, working memory, options), so it can be woken the same way
    last_run: dict = field(default_factory=dict)
    # Let the AI's web tools open addresses inside the user's own network (off: public internet only)
    allow_local_fetch: bool = False
    # Linked devices (datas.link): port of the encrypted link, share this device's memory with
    # them, keep chats in step between them
    link_port: int = 8424
    link_enabled: bool = False
    link_share_memory: bool = True
    link_sync_chats: bool = True
    device_name: str = ""

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
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (ValueError, OSError):
            # A damaged settings file (power cut, full disk) must not stop the app: keep it
            # aside for inspection, fall back to the last good copy, else start fresh.
            try:
                p.replace(p.with_name(CONFIG_PATH_NAME + ".damaged"))
            except OSError:
                pass
            bak = p.with_name(CONFIG_PATH_NAME + ".bak")
            try:
                data = json.loads(bak.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("not an object")
            except (ValueError, OSError):
                return cls()
        remotes = []
        for r in data.pop("remotes", []) or []:
            try:
                remotes.append(RemoteProviderConfig(**r))
            except TypeError:
                continue
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        try:
            cfg = cls(**known)
        except TypeError:
            cfg = cls()
        cfg.remotes = remotes
        return cfg

    def save(self) -> Path:
        """Written through a temporary file, keeping the previous good copy as ``.bak``."""
        p = home() / CONFIG_PATH_NAME
        # private: it holds API keys (no effect on Windows). Several parts of Datas save the
        # settings, sometimes at the same moment: write_text_safely keeps them apart.
        return write_text_safely(p, json.dumps(asdict(self), indent=2), private=True, backup=True)

    def remote(self, name: str) -> RemoteProviderConfig | None:
        for r in self.remotes:
            if r.name == name:
                return r
        return None
