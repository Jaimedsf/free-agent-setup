import json
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class LocalTier:
    min_free_mb: int
    max_free_mb: int | None
    model: str
    download_gb: float
    ctx: int


@dataclass(frozen=True)
class CloudCandidate:
    id: str
    kind: str
    model: str
    alias: str
    tier: str


@dataclass(frozen=True)
class Catalog:
    local_tiers: list[LocalTier]
    cloud: list[CloudCandidate]


def load_catalog() -> Catalog:
    data = json.loads((resources.files("freeagent") / "catalog.json").read_text(encoding="utf-8"))
    return Catalog(
        local_tiers=[LocalTier(**t) for t in data["local_tiers"]],
        cloud=[CloudCandidate(**c) for c in data["cloud"]],
    )
