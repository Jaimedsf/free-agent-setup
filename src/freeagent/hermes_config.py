"""Structured, idempotent edits to the Hermes config.yaml.

Only keys this tool wrote before (tracked in a state file) are replaced on a re-run, so entries the
person added by hand survive. Comments, BOM and line endings are preserved.
"""

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

LOCAL_TASKS = ("title_generation", "session_search", "web_extract")
_BOM = b"\xef\xbb\xbf"
_KEY = re.compile(r"^(\s*)(- )?([A-Za-z0-9_.-]+)\s*:(\s|$)")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Approved:
    alias: str
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    tier: str = "mid"


@dataclass(frozen=True)
class Selection:
    main: Approved
    fallbacks: list[Approved]
    local: Approved | None
    compression: Approved
    aliases: list[Approved]


def find_duplicate_keys(text: str) -> list[str]:
    dups: list[str] = []
    stack: list[tuple[int, str, set]] = [(-1, "", set())]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY.match(line)
        if not m:
            continue
        indent = len(m.group(1)) + (2 if m.group(2) else 0)
        while stack[-1][0] >= indent:
            stack.pop()
        if m.group(2):
            stack.append((indent - 1, stack[-1][1], set()))  # new list item = new mapping scope
        parent = stack[-1]
        key = m.group(3)
        path = f"{parent[1]}.{key}" if parent[1] else key
        if key in parent[2]:
            dups.append(path)
        parent[2].add(key)
        stack.append((indent, path, set()))
    return dups


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _read(path: Path) -> tuple[str, bool, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(_BOM)
    text = raw[len(_BOM):].decode("utf-8") if bom else raw.decode("utf-8")
    crlf = "\r\n" in text
    return text.replace("\r\n", "\n"), bom, crlf


def _write(path: Path, doc, bom: bool, crlf: bool) -> None:
    buf = io.StringIO()
    _yaml().dump(doc, buf)
    text = buf.getvalue()
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes((_BOM if bom else b"") + text.encode("utf-8"))


def _load_state(state_path: Path) -> dict:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _aux_provider(provider: str) -> str:
    # The auxiliary blocks name the Codex OAuth provider "codex"; the main model uses "openai-codex".
    return "codex" if provider == "openai-codex" else provider


def _endpoint(a: Approved, *, aux: bool) -> CommentedMap:
    m = CommentedMap()
    m["provider"] = _aux_provider(a.provider) if aux else a.provider
    if a.base_url:
        m["base_url"] = a.base_url
    if a.api_key:
        m["api_key"] = a.api_key
    m["model"] = a.model
    return m


def _last_slot(node):
    """(container, key, token index) of the deepest last item, where ruamel keeps trailing comments."""
    if isinstance(node, CommentedMap) and len(node):
        key = list(node)[-1]
        return _last_slot(node[key]) or (node, key, 2)
    if isinstance(node, CommentedSeq) and len(node):
        idx = len(node) - 1
        return _last_slot(node[idx]) or (node, idx, 0)
    return None


def _pop_tail(node):
    slot = _last_slot(node)
    if not slot:
        return None
    container, key, i = slot
    entry = container.ca.items.get(key)
    if not entry or len(entry) <= i or entry[i] is None:
        return None
    token, entry[i] = entry[i], None
    return token


def _put_tail(node, token) -> None:
    slot = _last_slot(node)
    if token is None or not slot:
        return
    container, key, i = slot
    entry = container.ca.items.setdefault(key, [None, None, None, None])
    while len(entry) <= i:
        entry.append(None)
    entry[i] = token


def _set_aliases(doc, aliases: list[Approved], state: dict) -> None:
    block = doc.get("model_aliases")
    if not isinstance(block, dict):
        block = CommentedMap()
        doc["model_aliases"] = block
    for name in state.get("aliases", []):
        block.pop(name, None)
    for a in aliases:
        block[a.alias] = _endpoint(a, aux=False)
    state["aliases"] = [a.alias for a in aliases]


def _load_doc(path: Path):
    text, bom, crlf = _read(path)
    dups = find_duplicate_keys(text)
    if dups:
        raise ConfigError("duplicate keys: " + ", ".join(dups))
    doc = _yaml().load(text) or CommentedMap()
    return doc, bom, crlf


EDITED_KEYS = ("model", "fallback_providers", "model_aliases", "auxiliary")


def _preserving_comments(doc, edit) -> None:
    """Run edit(doc) keeping the comments that trail each edited block and the end of the file."""
    doc_tail = _pop_tail(doc)
    tails = {k: _pop_tail(doc[k]) for k in EDITED_KEYS if k in doc}
    edit(doc)
    for key, token in tails.items():
        if key in doc:
            _put_tail(doc[key], token)
    _put_tail(doc, doc_tail)


def write_aliases(path: Path, aliases: list[Approved], state_path: Path) -> None:
    doc, bom, crlf = _load_doc(path)
    state = _load_state(state_path)
    _preserving_comments(doc, lambda d: _set_aliases(d, aliases, state))
    _write(path, doc, bom, crlf)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def apply_selection(path: Path, sel: Selection, state_path: Path) -> None:
    doc, bom, crlf = _load_doc(path)
    state = _load_state(state_path)
    _preserving_comments(doc, lambda d: _apply(d, sel, state))
    _write(path, doc, bom, crlf)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _apply(doc, sel: Selection, state: dict) -> None:
    model = doc.get("model")
    if not isinstance(model, dict):
        model = CommentedMap()
        doc["model"] = model
    model["default"] = sel.main.model
    model["provider"] = sel.main.provider
    model["base_url"] = sel.main.base_url or ""

    ours = [_endpoint(a, aux=False) for a in sel.fallbacks]
    previous = {tuple(p) for p in state.get("fallbacks", [])}
    existing = doc.get("fallback_providers") or []
    kept = [e for e in existing if (e.get("provider"), e.get("model")) not in previous]
    doc["fallback_providers"] = CommentedSeq(ours + kept)
    state["fallbacks"] = [[a.provider, a.model] for a in sel.fallbacks]

    _set_aliases(doc, sel.aliases, state)

    aux = doc.get("auxiliary")
    if not isinstance(aux, dict):
        aux = CommentedMap()
        doc["auxiliary"] = aux
    comp = _endpoint(sel.compression, aux=True)
    comp["reasoning_effort"] = "low"
    aux["compression"] = comp
    for task in LOCAL_TASKS:
        if sel.local:
            block = _endpoint(sel.local, aux=True)
            block["timeout"] = 120
            block["fallback_chain"] = CommentedSeq([_endpoint(sel.compression, aux=True)])
        else:
            block = _endpoint(sel.compression, aux=True)
        aux[task] = block
