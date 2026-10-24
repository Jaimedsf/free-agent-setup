import json
from functools import cache
from importlib import resources

LANGS = ("en", "pt")


@cache
def load(lang: str) -> dict[str, str]:
    return json.loads((resources.files(__package__) / f"{lang}.json").read_text(encoding="utf-8"))


def t(key: str, lang: str, **kw) -> str:
    text = load(lang if lang in LANGS else "en").get(key) or load("en").get(key) or key
    return text.format(**kw) if kw else text
