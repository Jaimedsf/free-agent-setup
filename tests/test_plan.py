from importlib import resources

import pytest

from freeagent.catalog import load_catalog
from freeagent.plan import make_plan
from freeagent.policy import forbidden_words
from tests.conftest import machine


@pytest.mark.parametrize(
    "free,model,ctx",
    [(3000, None, None), (4096, "bonsai-2:4b", 32768), (5000, "bonsai-2:4b", 32768),
     (6937, "bonsai-2:9b", 65536), (12000, "bonsai-2:9b", 131072), (20000, "bonsai-2:27b", 65536)],
)
def test_local_tier_by_free_vram(free, model, ctx):
    p = make_plan(machine(gpu_free=free), load_catalog())
    assert (p.local.model if p.local else None) == model
    assert (p.local.ctx if p.local else None) == ctx


def test_no_gpu_no_local():
    assert make_plan(machine(gpu=None), load_catalog()).local is None


def test_codex_candidates_only_when_logged_in():
    kinds = {c.kind for c in make_plan(machine(codex_logged_in=False), load_catalog()).cloud}
    assert "codex" not in kinds and {"nvidia", "ollama-cloud"} <= kinds


def test_codex_candidates_when_logged_in():
    kinds = [c.kind for c in make_plan(machine(codex_logged_in=True), load_catalog()).cloud]
    assert "codex" in kinds


def test_cloud_keeps_catalog_priority_order():
    ids = [c.id for c in make_plan(machine(codex_logged_in=True), load_catalog()).cloud]
    assert ids[:2] == ["nvidia-nemotron-ultra", "ollama-nemotron-ultra"]


def test_executor():
    assert make_plan(machine(codex_logged_in=True), load_catalog()).executor == "codex"
    assert make_plan(machine(codex_logged_in=False), load_catalog()).executor == "hermes"


def test_install_list_missing_only_and_ordered():
    p = make_plan(machine(hermes=False, omh=False, ollama=True), load_catalog())
    assert p.install == ["hermes", "omh"]


def test_install_all_in_order():
    assert make_plan(machine(), load_catalog()).install == ["ollama", "hermes", "omh"]


def test_ollama_installed_only_if_needed():
    p = make_plan(machine(gpu=None, ollama=False), load_catalog(), skip_cloud=True)
    assert "ollama" not in p.install


def test_skip_flags():
    p = make_plan(machine(gpu_free=7000), load_catalog(), skip_local=True, skip_cloud=True)
    assert p.local is None and p.cloud == []


def test_catalog_has_no_forbidden_vendor():
    text = (resources.files("freeagent") / "catalog.json").read_text().lower()
    assert not any(w in text for w in forbidden_words())
