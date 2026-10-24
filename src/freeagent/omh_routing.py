"""oh-my-hermes model routing built only from models that passed a probe on this machine."""

from freeagent.hermes_config import Approved
from freeagent.policy import EXCLUDED_EXECUTORS
from freeagent.runner import Runner

CATEGORIES = {
    "heavy": ("ultrabrain", "architect", "deep", "deep-work"),
    "mid": ("unspecified-high", "capable", "writing", "visual-engineering", "artistry"),
    "fast": ("unspecified-low", "quick", "simple-work"),
}
EFFORT = {
    "ultrabrain": "xhigh", "architect": "xhigh", "deep": "high", "deep-work": "high",
    **{c: "medium" for c in CATEGORIES["mid"]},
    **{c: "low" for c in CATEGORIES["fast"]},
}
_PREFERENCE = {
    "heavy": ("heavy", "mid", "fast"),
    "mid": ("mid", "heavy", "fast"),
    "fast": ("fast", "mid", "heavy"),
}


def _ordered(approved: list[Approved], level: str) -> list[Approved]:
    rank = {tier: i for i, tier in enumerate(_PREFERENCE[level])}
    return sorted(approved, key=lambda a: rank.get(a.tier, len(rank)))  # stable: keeps priority order


def _chains(approved: list[Approved], local: Approved | None) -> dict[str, list[str]]:
    chains = {}
    for level, cats in CATEGORIES.items():
        models = [a.model for a in _ordered(approved, level)]
        if level == "fast" and local:
            models.append(local.model)
        unique = list(dict.fromkeys(models))
        for cat in cats:
            chains[cat] = [f"{m}:{EFFORT[cat]}" for m in unique]
    return chains


def hermes_chains(approved: list[Approved], local: Approved | None) -> dict[str, list[str]]:
    """Chains for Hermes-native delegation.

    The local model goes last in the fast categories; verified on a real OMH install that
    `omh model-chains set quick "freeagent-local:low"` is accepted.
    """
    return _chains(approved, local)


def maestro_chains(codex_models: list[Approved]) -> dict[str, list[str]]:
    return _chains(codex_models, None) if codex_models else {}


def apply_omh(
    runner: Runner, executor: str, chains: dict, maestro: dict, *, global_args: list[str] = ()
) -> list[str]:
    omh = ["omh", *global_args]
    if executor in EXCLUDED_EXECUTORS:
        executor = "hermes"
    warnings = []
    r = runner.run([*omh, "setup", "--scope", "user", "--yes", "--no-interactive",
                    "--default-executor", executor], timeout=600)
    if r.code != 0:
        warnings.append(f"omh setup: exit {r.code}")
    for cat, chain in chains.items():
        r = runner.run([*omh, "model-chains", "set", cat, ", ".join(chain)], timeout=60)
        if r.code != 0:
            warnings.append(f"omh model-chains {cat}: exit {r.code}")
    for cat, chain in maestro.items():
        r = runner.run([*omh, "coding", "category-maestro", "set", "codex", cat, *chain], timeout=60)
        if r.code != 0:
            warnings.append(f"omh category-maestro {cat}: exit {r.code}")
    return warnings
