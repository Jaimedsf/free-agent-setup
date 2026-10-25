import json
from importlib import resources

import pytest

from freeagent.catalog import (
    DEFAULT_CATALOG_URL,
    SUPPORTED_KINDS,
    CatalogError,
    choose_catalog,
    load_catalog,
    parse_catalog,
    read_catalog,
)
from freeagent.policy import forbidden_words

BUNDLED = json.loads((resources.files("freeagent") / "catalog.json").read_text(encoding="utf-8"))


def _text(**cloud_overrides) -> str:
    data = json.loads(json.dumps(BUNDLED))
    data["cloud"][0].update(cloud_overrides)
    return json.dumps(data)


def test_bundled_catalog_only_uses_supported_kinds():
    cat = load_catalog()
    assert cat.source == "bundled" and {c.kind for c in cat.cloud} <= set(SUPPORTED_KINDS)


def test_unsupported_kind_fails_bundled_but_is_skipped_online():
    text = _text(kind="groq")
    with pytest.raises(CatalogError, match="unsupported kind 'groq'"):
        parse_catalog(text, "bundled", strict=True)
    cat = parse_catalog(text, "https://x", strict=False)
    assert BUNDLED["cloud"][0]["id"] not in [c.id for c in cat.cloud]
    assert len(cat.cloud) == len(BUNDLED["cloud"]) - 1


@pytest.mark.parametrize("override", [
    {"alias": "a b; rm -rf"}, {"model": "--help"}, {"tier": "ultra"}, {"id": 7},
])
def test_unsafe_or_malformed_entries_are_rejected(override):
    with pytest.raises(CatalogError):
        parse_catalog(_text(**override), "https://x", strict=False)


def test_duplicate_alias_rejected():
    data = json.loads(json.dumps(BUNDLED))
    data["cloud"][1]["alias"] = data["cloud"][0]["alias"]
    with pytest.raises(CatalogError, match="duplicate"):
        parse_catalog(json.dumps(data), "https://x", strict=False)


def test_excluded_vendor_rejected():
    with pytest.raises(CatalogError, match="vendor"):
        parse_catalog(_text(model=forbidden_words()[0] + "-x"), "https://x", strict=False)


def test_default_uses_online_catalog_when_valid():
    online = _text(model="newer-model")
    cat, problem = choose_catalog(None, fetch=lambda url: online if url == DEFAULT_CATALOG_URL else "")
    assert problem is None and cat.source == DEFAULT_CATALOG_URL and cat.cloud[0].model == "newer-model"


@pytest.mark.parametrize("fetch_result", ["not json", json.dumps({"cloud": []})])
def test_default_falls_back_to_bundled(fetch_result):
    cat, problem = choose_catalog(None, fetch=lambda url: fetch_result)
    assert cat.source == "bundled" and problem


def test_default_falls_back_when_offline():
    cat, problem = choose_catalog(None)
    assert cat.source == "bundled" and problem == "offline in tests"


def test_explicit_sources(tmp_path):
    f = tmp_path / "catalog.json"
    f.write_text(_text(model="from-file"), encoding="utf-8")
    assert choose_catalog(str(f))[0].cloud[0].model == "from-file"
    assert choose_catalog("bundled") == (load_catalog(), None)
    with pytest.raises(CatalogError, match="https"):
        read_catalog("http://example.com/catalog.json")
    with pytest.raises(CatalogError, match="could not read"):
        choose_catalog(str(tmp_path / "missing.json"))
