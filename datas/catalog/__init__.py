"""Curated model catalog (schema + loader).

The catalog is a plain JSON manifest shipped with the package (``models.json``) and
optionally overridden/extended by a user file at ``~/.local/share/datas/catalog.json``.
Every entry points at a Hugging Face GGUF repo and lists the files with their exact
byte sizes as read from the HF API. See ``docs/CATALOG.md``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from datas.config import home

Quant = str

# Approximate bits per weight for common GGUF quant types. Used ONLY to derive a param
# count when the catalog does not state one (params = bytes*8 / bpw). Values are the
# widely published nominal densities of each type, not measurements of a given file.
BITS_PER_WEIGHT: dict[str, float] = {
    "F32": 32.0,
    "F16": 16.0,
    "BF16": 16.0,
    "Q8_0": 8.5,
    "Q6_K": 6.56,
    "Q5_K_M": 5.69,
    "Q5_K_S": 5.54,
    "Q5_0": 5.5,
    "Q4_K_M": 4.85,
    "Q4_K_S": 4.58,
    "Q4_0": 4.55,
    "Q4_1": 5.0,
    "IQ4_NL": 4.5,
    "IQ4_XS": 4.25,
    "MXFP4": 4.25,
    "Q3_K_M": 3.91,
    "Q3_K_S": 3.5,
    "Q3_K_L": 4.27,
    "IQ3_XXS": 3.06,
    "Q2_K": 3.35,
    "Q2_K_L": 3.4,
    "IQ2_XXS": 2.06,
    "IQ2_M": 2.7,
    "IQ1_M": 1.75,
    "IQ1_S": 1.56,
    "UD-Q2_K_XL": 3.5,
    "UD-Q3_K_XL": 4.3,
    "UD-Q4_K_XL": 5.0,
    "UD-Q5_K_XL": 6.0,
    "UD-Q6_K_XL": 7.0,
    "UD-Q8_K_XL": 9.0,
    "UD-IQ4_XS": 4.3,
    "UD-IQ4_NL": 4.5,
}


class KVHint(BaseModel):
    layers: int
    kv_heads: int
    head_dim: int

    def bytes_per_token(self, cache_bits: int = 16) -> int:
        # K and V, every layer, every KV head, head_dim elements each.
        return 2 * self.layers * self.kv_heads * self.head_dim * (cache_bits // 8)


class ExtraFile(BaseModel):
    path: str
    bytes: int


class ModelFile(BaseModel):
    quant: Quant
    path: str
    bytes: int
    verified: str | None = None  # ISO date the size was read from the HF API

    @property
    def gib(self) -> float:
        return self.bytes / 2**30


class CatalogModel(BaseModel):
    id: str
    name: str
    family: str
    vendor: str
    params_b: float | None = None
    active_params_b: float | None = None
    arch: str = "dense"  # dense | moe
    license: str
    license_url: str | None = None
    license_source: str = "unverified"
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    capabilities: list[str] = Field(default_factory=lambda: ["chat"])
    quality_tier: int = 3
    role: str = (
        "general"  # general | coding | vision | embedding — specialists are never the default pick
    )
    tags: list[str] = Field(default_factory=list)
    vendor_url: str | None = None
    limits: str | None = None  # plain-language limits for non-technical users
    use_cases: list[str] = Field(
        default_factory=lambda: ["text"]
    )  # text | images | coding | agents
    hf_repo: str
    # set when another team tuned this model from a base model (shown on the card; at equal
    # quality and speed the recommender prefers the original)
    finetune_of: str | None = None
    kv: KVHint | None = None
    files: list[ModelFile]
    extras: dict[str, ExtraFile] = Field(default_factory=dict)
    note: str | None = None

    @field_validator("quality_tier")
    @classmethod
    def _tier_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("quality_tier must be 1..5")
        return v

    def file(self, quant: str) -> ModelFile:
        for f in self.files:
            if f.quant.lower() == quant.lower():
                return f
        raise KeyError(
            f"{self.id} has no quant {quant!r}; available: {[f.quant for f in self.files]}"
        )

    def smallest(self) -> ModelFile:
        return min(self.files, key=lambda f: f.bytes)

    def params_estimate(self, f: ModelFile) -> float:
        """Billions of parameters, from the catalog or derived from the file size."""
        if self.params_b:
            return self.params_b
        bpw = BITS_PER_WEIGHT.get(f.quant.upper(), 4.85)
        return (f.bytes * 8 / bpw) / 1e9

    def active_estimate(self, f: ModelFile) -> float:
        if self.active_params_b:
            return self.active_params_b
        if self.arch == "moe":
            # Unknown MoE activation ratio: assume a conservative 1/8 of total.
            return self.params_estimate(f) / 8
        return self.params_estimate(f)

    @property
    def hf_url(self) -> str:
        return f"https://huggingface.co/{self.hf_repo}"


class Catalog(BaseModel):
    schema_version: int = 1
    generated: str | None = None
    notes: list[str] = Field(default_factory=list)
    models: list[CatalogModel]

    def get(self, model_id: str) -> CatalogModel:
        for m in self.models:
            if m.id == model_id:
                return m
        raise KeyError(f"unknown model id {model_id!r}")

    def ids(self) -> list[str]:
        return [m.id for m in self.models]


def bundled_path() -> Path:
    return Path(str(resources.files("datas.catalog").joinpath("models.json")))


def user_path() -> Path:
    return home() / "catalog.json"


def update_path() -> Path:
    """A newer list fetched from the project on request (Settings → Updates). The bundled list
    is never modified; deleting this file goes back to it."""
    return home() / "catalog.update.json"


@lru_cache(maxsize=1)
def load() -> Catalog:
    """The newest of {bundled list, updated list}, merged with the user's catalog.json
    (user entries win by id)."""
    base = Catalog.model_validate_json(bundled_path().read_text(encoding="utf-8"))
    upd = update_path()
    if upd.exists():
        try:
            newer = Catalog.model_validate_json(upd.read_text(encoding="utf-8"))
            if newer.models and (newer.generated or "") > (base.generated or ""):
                base = newer
        except (ValueError, OSError):
            pass  # a damaged update file is ignored: the bundled list always works
    up = user_path()
    if up.exists():
        user = Catalog.model_validate_json(up.read_text())
        by_id = {m.id: m for m in base.models}
        for m in user.models:
            by_id[m.id] = m
        base = Catalog(
            schema_version=base.schema_version,
            generated=base.generated,
            notes=base.notes,
            models=list(by_id.values()),
        )
    return base


def reload() -> Catalog:
    load.cache_clear()
    return load()


def add_user_model(entry: dict) -> CatalogModel:
    """Append/replace a model in the user's catalog.json and return it validated."""
    m = CatalogModel.model_validate(entry)
    up = user_path()
    data = json.loads(up.read_text()) if up.exists() else {"schema_version": 1, "models": []}
    data["models"] = [x for x in data["models"] if x.get("id") != m.id] + [
        m.model_dump(exclude_none=True)
    ]
    up.write_text(json.dumps(data, indent=2))
    reload()
    return m
