"""The model catalog: bundled with the package, and by default refreshed from the repository.

Free tiers change faster than releases, so the catalog on `main` is tried first; any fetch or validation
failure falls back to the bundled copy. Every catalog is validated before use, since its names end up in
the Hermes config and on command lines.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from freeagent.policy import forbidden_words

DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/src/freeagent/catalog.json"
# Kinds this version knows how to log in to and probe. A newer catalog's other kinds are skipped.
SUPPORTED_KINDS = ("nvidia", "gemini", "ollama-cloud", "codex")
TIERS = ("fast", "mid", "heavy")
MAX_BYTES = 256 * 1024
_ID = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")


class CatalogError(ValueError):
    pass


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
    source: str = "bundled"


def _field(raw: dict, key: str, ok, what: str):
    if key not in raw or not ok(raw[key]):
        raise CatalogError(f"{key}: expected {what}, got {raw.get(key)!r}")
    return raw[key]


def _int(v) -> bool:
    return type(v) is int and v >= 0


def _name(pattern: re.Pattern):
    return lambda v: isinstance(v, str) and pattern.fullmatch(v) is not None


def _local_tier(raw) -> LocalTier:
    if not isinstance(raw, dict):
        raise CatalogError("local tier must be an object")
    return LocalTier(
        min_free_mb=_field(raw, "min_free_mb", _int, "a non-negative integer"),
        max_free_mb=_field(raw, "max_free_mb", lambda v: v is None or _int(v), "an integer or null"),
        model=_field(raw, "model", _name(_MODEL), "a model name"),
        download_gb=_field(raw, "download_gb", lambda v: type(v) in (int, float) and v > 0, "a size in GB"),
        ctx=_field(raw, "ctx", lambda v: _int(v) and v > 0, "a context length"),
    )


def _cloud(raw) -> CloudCandidate:
    if not isinstance(raw, dict):
        raise CatalogError("cloud candidate must be an object")
    return CloudCandidate(
        id=_field(raw, "id", _name(_ID), "an id"),
        kind=_field(raw, "kind", _name(_ID), "a provider kind"),
        model=_field(raw, "model", _name(_MODEL), "a model name"),
        alias=_field(raw, "alias", _name(_ID), "an alias"),
        tier=_field(raw, "tier", lambda v: v in TIERS, " / ".join(TIERS)),
    )


def parse_catalog(text: str, source: str, *, strict: bool) -> Catalog:
    """strict: an unsupported kind is an error (the bundled catalog) instead of being skipped (a newer one)."""
    lowered = text.lower()
    if any(w in lowered for w in forbidden_words()):
        raise CatalogError("names a vendor this project leaves out")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise CatalogError(f"not valid JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("local_tiers"), list) \
            or not isinstance(data.get("cloud"), list):
        raise CatalogError("expected an object with 'local_tiers' and 'cloud' lists")
    tiers = [_local_tier(x) for x in data["local_tiers"]]
    cloud: list[CloudCandidate] = []
    for c in map(_cloud, data["cloud"]):
        if c.kind not in SUPPORTED_KINDS:
            if strict:
                raise CatalogError(f"{c.id}: unsupported kind {c.kind!r} (supported: {', '.join(SUPPORTED_KINDS)})")
            continue
        if any(c.id == o.id or c.alias == o.alias for o in cloud):
            raise CatalogError(f"{c.id}: duplicate id or alias")
        cloud.append(c)
    if not tiers or not cloud:
        raise CatalogError("no usable local tiers or cloud candidates")
    return Catalog(local_tiers=tiers, cloud=cloud, source=source)


def load_catalog() -> Catalog:
    text = (resources.files("freeagent") / "catalog.json").read_text(encoding="utf-8")
    return parse_catalog(text, "bundled", strict=True)


def _fetch(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError) as e:
        raise CatalogError(f"could not download: {e}") from e
    if len(body) > MAX_BYTES:
        raise CatalogError("larger than expected")
    return body.decode("utf-8", errors="replace")


def read_catalog(source: str, fetch=None) -> Catalog:
    """Load a catalog from an https URL or a local file; raises CatalogError on any problem."""
    if source.startswith("https://"):
        text = (fetch or _fetch)(source)
    elif "://" in source:
        raise CatalogError("only https:// URLs are accepted")
    else:
        try:
            text = Path(source).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise CatalogError(f"could not read: {e}") from e
    return parse_catalog(text, source, strict=False)


def choose_catalog(source: str | None, fetch=None) -> tuple[Catalog, str | None]:
    """The catalog to use and, when the default online one was not usable, why.

    An explicit --catalog that fails raises: the person asked for that one, so a silent fallback would mislead.
    """
    if source == "bundled":
        return load_catalog(), None
    if source:
        return read_catalog(source, fetch), None
    try:
        return read_catalog(DEFAULT_CATALOG_URL, fetch), None
    except CatalogError as e:
        return load_catalog(), str(e)
