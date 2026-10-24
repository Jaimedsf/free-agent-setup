import re

_PATTERNS = [
    re.compile(r"Bearer\s+\S+"),
    re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"),
    re.compile(r"nvapi-[\w-]{8,}"),
    re.compile(r"sk-[\w-]{16,}"),
    re.compile(r"gh[pousr]_\w{20,}"),
]


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub("***", text)
    return text
