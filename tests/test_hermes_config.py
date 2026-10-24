import json

import pytest
from ruamel.yaml import YAML

from freeagent.hermes_config import Approved, ConfigError, Selection, apply_selection, find_duplicate_keys
from tests.conftest import FIXTURES

OLLAMA = "http://127.0.0.1:11434/v1"


def yaml_load(path):
    return YAML(typ="safe").load(path.read_text(encoding="utf-8-sig"))


def copy_fixture(tmp_path, *, crlf=False, bom=False, extra_alias=None):
    text = (FIXTURES / "config_sample.yaml").read_text(encoding="utf-8")
    if extra_alias:
        text += f"\nmodel_aliases:\n  {extra_alias}:\n    model: x\n    provider: custom\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    data = text.encode()
    if bom:
        data = b"\xef\xbb\xbf" + data
    path = tmp_path / "config.yaml"
    path.write_bytes(data)
    return path


def sel(*, aliases=("nemotron", "local"), local="default"):
    main = Approved("nemotron", "nvidia", "nvidia/nemotron-3-ultra-550b-a55b", tier="heavy")
    fb = Approved("nemotron-ollama", "custom", "nemotron-3-ultra:cloud", OLLAMA, "ollama", "heavy")
    comp = Approved("codex-gpt-reserve", "openai-codex", "gpt-reserve", tier="fast")
    loc = local
    if local == "default":
        loc = Approved("local", "custom", "freeagent-local", OLLAMA, "ollama", "fast")
    pool = {a.alias: a for a in (main, fb, comp, loc) if a}
    al = [pool.get(n) or Approved(n, "custom", n + "-model", OLLAMA, "ollama") for n in aliases]
    return Selection(main=main, fallbacks=[fb, comp], local=loc, compression=comp, aliases=al)


def test_preserves_comments_and_real_alias_block(tmp_path):
    cfg = copy_fixture(tmp_path)
    apply_selection(cfg, sel(), tmp_path / "s.json")
    text = cfg.read_text(encoding="utf-8-sig")
    assert "# model_aliases:" in text and "# Default model to use" in text
    data = yaml_load(cfg)
    assert data["model_aliases"]["nemotron"]["provider"] == "nvidia"
    assert data["memory"] == {"provider": "omh"}


def test_main_model_written(tmp_path):
    cfg = copy_fixture(tmp_path)
    apply_selection(cfg, sel(), tmp_path / "s.json")
    m = yaml_load(cfg)["model"]
    assert m == {"default": "nvidia/nemotron-3-ultra-550b-a55b", "provider": "nvidia", "base_url": ""}


def test_fallbacks_and_aux(tmp_path):
    cfg = copy_fixture(tmp_path)
    apply_selection(cfg, sel(), tmp_path / "s.json")
    d = yaml_load(cfg)
    assert [f["model"] for f in d["fallback_providers"]] == ["nemotron-3-ultra:cloud", "gpt-reserve"]
    comp = {"provider": "codex", "model": "gpt-reserve", "reasoning_effort": "low"}
    assert d["auxiliary"]["compression"] == comp
    t = d["auxiliary"]["title_generation"]
    assert t["base_url"] == OLLAMA and t["model"] == "freeagent-local" and t["timeout"] == 120
    assert t["fallback_chain"] == [{"provider": "codex", "model": "gpt-reserve"}]


def test_rerun_is_idempotent(tmp_path):
    cfg = copy_fixture(tmp_path)
    st = tmp_path / "s.json"
    apply_selection(cfg, sel(), st)
    first = cfg.read_bytes()
    apply_selection(cfg, sel(), st)
    assert cfg.read_bytes() == first
    assert find_duplicate_keys(cfg.read_text("utf-8-sig")) == []


def test_rerun_replaces_only_own_aliases(tmp_path):
    cfg = copy_fixture(tmp_path, extra_alias="mine")
    st = tmp_path / "s.json"
    apply_selection(cfg, sel(aliases=["a", "b"]), st)
    apply_selection(cfg, sel(aliases=["a"]), st)
    assert set(yaml_load(cfg)["model_aliases"]) == {"mine", "a"}


def test_rerun_keeps_user_fallbacks(tmp_path):
    cfg = copy_fixture(tmp_path)
    cfg.write_text(cfg.read_text() + "\nfallback_providers:\n  - provider: mine\n    model: m1\n")
    st = tmp_path / "s.json"
    apply_selection(cfg, sel(), st)
    apply_selection(cfg, sel(), st)
    models = [f["model"] for f in yaml_load(cfg)["fallback_providers"]]
    assert models == ["nemotron-3-ultra:cloud", "gpt-reserve", "m1"]
    assert json.loads(st.read_text())["fallbacks"]


def test_crlf_and_bom_preserved(tmp_path):
    cfg = copy_fixture(tmp_path, crlf=True, bom=True)
    apply_selection(cfg, sel(), tmp_path / "s.json")
    raw = cfg.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert yaml_load(cfg)["model"]["provider"] == "nvidia"


def test_detects_preexisting_duplicate():
    assert find_duplicate_keys("plugins:\n  enabled: []\n  enabled: [x]\n") == ["plugins.enabled"]


def test_list_items_are_separate_scopes():
    text = "fb:\n  - provider: a\n    model: x\n  - provider: b\n    model: y\n"
    assert find_duplicate_keys(text) == []


def test_comments_are_not_keys():
    assert find_duplicate_keys("# model_aliases:\nmodel_aliases:\n  a: 1\n") == []


def test_duplicate_aborts_before_write(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("plugins:\n  enabled: []\n  enabled: [x]\n")
    with pytest.raises(ConfigError):
        apply_selection(cfg, sel(), tmp_path / "s.json")
    assert cfg.read_text() == "plugins:\n  enabled: []\n  enabled: [x]\n"


def test_aux_without_local_uses_compression(tmp_path):
    cfg = copy_fixture(tmp_path)
    apply_selection(cfg, sel(local=None, aliases=["nemotron"]), tmp_path / "s.json")
    t = yaml_load(cfg)["auxiliary"]["title_generation"]
    assert t["model"] == "gpt-reserve" and "fallback_chain" not in t


TRAILING = """model_aliases:
  old:
    model: m
    provider: custom

# =====
# Privacy section
# =====
privacy:
  redact_pii: false

auxiliary:
  web_extract:
    provider: auto

# Trailing note after auxiliary
memory:
  provider: omh

fallback_providers:
  - provider: x
    model: y

# Comment after fallbacks
updates:
  check: false
"""


def test_comments_after_replaced_blocks_survive(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(TRAILING)
    st = tmp_path / "s.json"
    st.write_text(json.dumps({"aliases": ["old"], "fallbacks": [["x", "y"]]}))
    apply_selection(cfg, sel(), st)
    text = cfg.read_text()
    for c in ("# Privacy section", "# Trailing note after auxiliary", "# Comment after fallbacks"):
        assert c in text
    assert text.index("# Privacy section") < text.index("privacy:")
    assert text.index("# Comment after fallbacks") < text.index("updates:")
