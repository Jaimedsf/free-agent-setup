from dataclasses import dataclass, field

from freeagent.catalog import Catalog, CloudCandidate, LocalTier
from freeagent.detect import Machine


@dataclass(frozen=True)
class Plan:
    local: LocalTier | None
    cloud: list[CloudCandidate]
    install: list[str]
    executor: str
    notes: list[str] = field(default_factory=list)


def local_tier(free_mb: int, tiers: list[LocalTier]) -> LocalTier | None:
    for tier in tiers:
        if free_mb >= tier.min_free_mb and (tier.max_free_mb is None or free_mb <= tier.max_free_mb):
            return tier
    return None


def make_plan(m: Machine, cat: Catalog, *, skip_local: bool = False, skip_cloud: bool = False) -> Plan:
    local = None if skip_local or m.gpu is None else local_tier(m.gpu.vram_free_mb, cat.local_tiers)
    cloud = [] if skip_cloud else [
        c for c in cat.cloud if c.kind != "codex" or m.tools.codex_logged_in
    ]
    notes = []
    if m.gpu is None and not skip_local:
        notes.append("notes.no_gpu")
    elif local is None and not skip_local:
        notes.append("notes.gpu_too_small")
    needs_ollama = local is not None or any(c.kind == "ollama-cloud" for c in cloud)
    present = {"ollama": m.tools.ollama, "hermes": m.tools.hermes, "omh": m.tools.omh}
    install = [
        name for name in ("ollama", "hermes", "omh")
        if not present[name] and (name != "ollama" or needs_ollama)
    ]
    executor = "codex" if m.tools.codex_logged_in else "hermes"
    return Plan(local=local, cloud=cloud, install=install, executor=executor, notes=notes)
