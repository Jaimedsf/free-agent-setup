import pytest

from freeagent.policy import forbidden_words
from scripts.privacy_scan import scan

U = "Users"


@pytest.mark.parametrize("line", [
    "C:\\" + U + r"\someone\AppData",
    "/home/" + "someone/.hermes",
    "mail me at person" + "@example.com",
    "key nvapi" + "-abcdefgh12",
    "sk" + "-abcdefghijklmnopqrst",
    "gh" + "o_" + "a" * 24,
])
def test_scan_flags(tmp_path, line):
    f = tmp_path / "x.md"
    f.write_text(line + "\n")
    assert len(scan([f])) == 1


def test_scan_flags_forbidden_words(tmp_path):
    f = tmp_path / "x.md"
    f.write_text(f"uses {forbidden_words()[1].capitalize()} models\n")
    assert scan([f]) and "forbidden" in scan([f])[0]


@pytest.mark.parametrize("line", [
    r"%LOCALAPPDATA%\hermes",
    "~/.hermes and $HOME/.profile",
    "31625431+Jaimedsf" + "@users.noreply.github.com",
    "C:\\" + U + r"\%USERNAME%\x",
    "/home/runner/work",
    "uses: astral-sh/setup-uv@v10.3.2",
])
def test_scan_allows(tmp_path, line):
    f = tmp_path / "x.md"
    f.write_text(line + "\n")
    assert scan([f]) == []


def test_scan_reports_file_and_line(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("ok\n/home/" + "bob/x\n")
    assert scan([f])[0].startswith(f"{f}:2:")
