from freeagent.catalog import load_catalog
from freeagent.plan import make_plan
from freeagent.probe import LocalResult, ProbeResult
from freeagent.select import select
from tests.conftest import machine


def _results(plan, ok_ids):
    return [(c, ProbeResult(c.id, c.id in ok_ids, 1.0 if c.id in ok_ids else None,
                            "ok" if c.id in ok_ids else "http_402")) for c in plan.cloud]


LOCAL = LocalResult("bonsai-2:9b", 65536, 100, 92.0)


def test_select_order_and_fallbacks():
    plan = make_plan(machine(codex_logged_in=True), load_catalog())
    sel = select(plan, _results(plan, {"ollama-nemotron-ultra", "nvidia-nemotron-ultra", "codex-gpt-6-luna"}), LOCAL)
    assert sel.main.provider == "nvidia" and sel.main.model == "nvidia/nemotron-3-ultra-550b-a55b"
    assert [f.alias for f in sel.fallbacks] == ["nemotron-ollama", "codex-gpt-6-luna"]
    assert sel.fallbacks[0].base_url == "http://127.0.0.1:11434/v1" and sel.fallbacks[0].provider == "custom"
    assert sel.fallbacks[1].provider == "openai-codex"
    assert sel.compression.alias == "nemotron"
    assert sel.local.model == "freeagent-local" and "local" in [a.alias for a in sel.aliases]


def test_select_local_as_main_when_no_cloud():
    plan = make_plan(machine(), load_catalog())
    sel = select(plan, _results(plan, set()), LOCAL)
    assert sel.main.model == "freeagent-local" and sel.compression.model == "freeagent-local"
    assert sel.fallbacks == []


def test_select_none():
    plan = make_plan(machine(), load_catalog())
    assert select(plan, _results(plan, set()), None) is None
