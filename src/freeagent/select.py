from freeagent.catalog import CloudCandidate
from freeagent.hermes_config import Approved, Selection
from freeagent.plan import Plan
from freeagent.probe import LOCAL_NAME, OLLAMA_BASE, LocalResult, ProbeResult

OLLAMA_V1 = OLLAMA_BASE + "/v1"


def approved_from(c: CloudCandidate) -> Approved:
    if c.kind == "ollama-cloud":
        return Approved(c.alias, "custom", c.model, OLLAMA_V1, "ollama", c.tier)
    if c.kind == "codex":
        return Approved(c.alias, "openai-codex", c.model, tier=c.tier)
    return Approved(c.alias, c.kind, c.model, tier=c.tier)


def local_approved() -> Approved:
    return Approved("local", "custom", LOCAL_NAME, OLLAMA_V1, "ollama", "fast")


def select(plan: Plan, results: list[tuple[CloudCandidate, ProbeResult]],
           local: LocalResult | None) -> Selection | None:
    order = {c.id: i for i, c in enumerate(plan.cloud)}
    passed = [approved_from(c) for c, r in sorted(results, key=lambda cr: order.get(cr[0].id, 99)) if r.ok]
    loc = local_approved() if local else None
    if not passed and not loc:
        return None
    main = passed[0] if passed else loc
    return Selection(
        main=main,
        fallbacks=passed[1:],
        local=loc,
        compression=passed[0] if passed else loc,
        aliases=passed + ([loc] if loc else []),
    )
