"""Read exact architecture facts from a GGUF header (no inference, no full load).

Reuses the ``gguf`` package maintained inside llama.cpp. Once a model is on disk we
replace the recommender's KV-cache estimate with the real per-token size and learn the
training context length, so the context slider never exceeds what the model supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from datas.catalog import KVHint


@dataclass
class GGUFFacts:
    architecture: str
    name: str | None
    layers: int | None
    kv_heads: int | None
    head_dim: int | None
    context_train: int | None
    file_type: int | None
    expert_count: int | None
    experts_used: int | None

    def kv_hint(self) -> KVHint | None:
        if self.layers and self.kv_heads and self.head_dim:
            return KVHint(layers=self.layers, kv_heads=self.kv_heads, head_dim=self.head_dim)
        return None

    def to_dict(self) -> dict:
        return self.__dict__ | {
            "kv_bytes_per_token_f16": (
                self.kv_hint().bytes_per_token(16) if self.kv_hint() else None
            )
        }


def _scalar(reader, key: str):
    f = reader.fields.get(key)
    if f is None or not f.data:
        return None
    v = f.parts[f.data[0]]
    try:
        if hasattr(v, "tobytes") and f.types and f.types[0].name == "STRING":
            return bytes(v).decode("utf-8", errors="replace")
        return v[0].item() if hasattr(v[0], "item") else v[0]
    except Exception:
        return None


def _first(reader, keys: list[str]):
    for k in keys:
        v = _scalar(reader, k)
        if v is not None:
            return v
    return None


def read(path: Path) -> GGUFFacts:
    from gguf import GGUFReader  # lazy: importing numpy-backed reader is slow

    r = GGUFReader(str(path))
    arch = _scalar(r, "general.architecture") or "unknown"
    layers = _scalar(r, f"{arch}.block_count")
    kv_heads = _first(r, [f"{arch}.attention.head_count_kv", f"{arch}.attention.head_count"])
    head_dim = _first(r, [f"{arch}.attention.key_length"])
    if head_dim is None:
        emb = _scalar(r, f"{arch}.embedding_length")
        heads = _scalar(r, f"{arch}.attention.head_count")
        if emb and heads:
            head_dim = int(emb) // int(heads)
    # Per-layer kv head arrays (e.g. hybrid attention) → take the max for a safe estimate
    f = r.fields.get(f"{arch}.attention.head_count_kv")
    if f is not None and f.data and len(f.data) > 1:
        try:
            kv_heads = int(max(f.parts[i][0] for i in f.data))
        except Exception:
            pass
    return GGUFFacts(
        architecture=str(arch),
        name=_scalar(r, "general.name"),
        layers=int(layers) if layers is not None else None,
        kv_heads=int(kv_heads) if kv_heads is not None else None,
        head_dim=int(head_dim) if head_dim is not None else None,
        context_train=(lambda v: int(v) if v is not None else None)(
            _scalar(r, f"{arch}.context_length")
        ),
        file_type=(lambda v: int(v) if v is not None else None)(_scalar(r, "general.file_type")),
        expert_count=(lambda v: int(v) if v is not None else None)(
            _scalar(r, f"{arch}.expert_count")
        ),
        experts_used=(lambda v: int(v) if v is not None else None)(
            _scalar(r, f"{arch}.expert_used_count")
        ),
    )
