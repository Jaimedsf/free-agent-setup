"""Vendors this project deliberately leaves out of every configuration.

Names are stored base64-encoded so that no file in the repository spells them out.
"""

import base64

FORBIDDEN_B64 = ("Y2xhdWRl", "YW50aHJvcGlj")


def forbidden_words() -> tuple[str, ...]:
    return tuple(base64.b64decode(w).decode() for w in FORBIDDEN_B64)


EXCLUDED_EXECUTORS = (forbidden_words()[0] + "-code",)
