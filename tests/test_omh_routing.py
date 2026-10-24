from freeagent.hermes_config import Approved
from freeagent.omh_routing import CATEGORIES, EFFORT, apply_omh, hermes_chains, maestro_chains
from freeagent.runner import RunResult

HEAVY = Approved("nemotron", "nvidia", "nvidia/nemotron-3-ultra-550b-a55b", tier="heavy")
MID = Approved("gemma-cloud", "custom", "gemma4:31b-cloud", tier="mid")
FAST = Approved("codex-gpt-reserve", "openai-codex", "gpt-reserve", tier="fast")
LOCAL = Approved("local", "custom", "freeagent-local", tier="fast")
ALL_CATS = [c for cats in CATEGORIES.values() for c in cats]


def test_every_category_present():
    chains = hermes_chains([FAST, HEAVY, MID], LOCAL)
    assert sorted(chains) == sorted(ALL_CATS) and len(ALL_CATS) == 12


def test_heavy_prefers_heavy_tier():
    chains = hermes_chains([FAST, HEAVY], None)
    assert chains["ultrabrain"][0] == "nvidia/nemotron-3-ultra-550b-a55b:xhigh"
    assert chains["deep"][0].endswith(":high")


def test_mid_prefers_mid_then_heavy():
    assert hermes_chains([FAST, HEAVY, MID], None)["capable"][:2] == [
        "gemma4:31b-cloud:medium", "nvidia/nemotron-3-ultra-550b-a55b:medium"]


def test_fast_prefers_fast_then_local_last():
    chain = hermes_chains([HEAVY, FAST], LOCAL)["quick"]
    assert chain[0] == "gpt-reserve:low" and chain[-1] == "freeagent-local:low"


def test_no_duplicates_per_chain():
    for chain in hermes_chains([HEAVY, HEAVY, FAST], LOCAL).values():
        assert len(chain) == len(set(chain))


def test_effort_table():
    assert EFFORT["ultrabrain"] == "xhigh" and EFFORT["capable"] == "medium" and EFFORT["quick"] == "low"


def test_apply_commands(fake_runner):
    fake_runner.default = RunResult(0, "", "")
    apply_omh(fake_runner, "codex", hermes_chains([HEAVY], None), maestro_chains([FAST]))
    args = [c["args"] for c in fake_runner.calls]
    assert args[0] == ["omh", "setup", "--scope", "user", "--yes", "--no-interactive",
                       "--default-executor", "codex"]
    assert sum(a[:3] == ["omh", "model-chains", "set"] for a in args) == 12
    assert sum(a[:4] == ["omh", "coding", "category-maestro", "set"] for a in args) == 12


def test_maestro_skipped_without_codex(fake_runner):
    fake_runner.default = RunResult(0, "", "")
    assert maestro_chains([]) == {}
    apply_omh(fake_runner, "hermes", hermes_chains([HEAVY], None), {})
    assert not any("category-maestro" in c["args"] for c in fake_runner.calls)


def test_apply_reports_failures(fake_runner):
    fake_runner.default = RunResult(0, "", "")
    fake_runner.set(("omh", "model-chains", "set", "quick"), RunResult(2, "", "bad"))
    warnings = apply_omh(fake_runner, "hermes", hermes_chains([HEAVY], None), {})
    assert any("quick" in w for w in warnings)


def test_excluded_executor_never_used(fake_runner):
    from freeagent.policy import EXCLUDED_EXECUTORS
    fake_runner.default = RunResult(0, "", "")
    apply_omh(fake_runner, EXCLUDED_EXECUTORS[0], {}, {})
    assert fake_runner.calls[0]["args"][-1] == "hermes"


def test_global_args_prefix_every_call(fake_runner):
    fake_runner.default = RunResult(0, "", "")
    apply_omh(fake_runner, "hermes", hermes_chains([HEAVY], None), {},
              global_args=["--omh-home", "/o", "--hermes-home", "/h"])
    assert all(c["args"][1:5] == ["--omh-home", "/o", "--hermes-home", "/h"] for c in fake_runner.calls)
