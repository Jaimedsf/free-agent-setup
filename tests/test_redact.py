import pytest

from freeagent.policy import EXCLUDED_EXECUTORS, forbidden_words
from freeagent.redact import redact


@pytest.mark.parametrize(
    "raw",
    [
        "nvapi" + "-AbC123_x-9",
        "sk" + "-proj-abcdefghijklmnop",
        "Bearer " + "eyJ" + "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
    ],
)
def test_redact_masks(raw):
    out = redact(f"key={raw} done")
    assert raw not in out and "***" in out and out.endswith(" done")


def test_redact_keeps_normal_text():
    assert redact("model gpt-6-luna ok") == "model gpt-6-luna ok"


def test_policy_words_decoded_and_lowercase():
    words = forbidden_words()
    assert len(words) == 2 and all(w.isalpha() and w == w.lower() for w in words)
    assert EXCLUDED_EXECUTORS == (words[0] + "-code",)
