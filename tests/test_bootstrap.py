import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = [ROOT / "install.ps1", ROOT / "install.sh"]
ALLOWED = ("https://astral.sh/", "https://github.com/Jaimedsf/free-agent-setup",
           "https://raw.githubusercontent.com/Jaimedsf/free-agent-setup")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_bootstrap_scripts_small(script):
    lines = [ln for ln in script.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert 0 < len(lines) <= 60


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_bootstrap_urls_official(script):
    urls = re.findall(r"https://[^\s\"')]+", script.read_text(encoding="utf-8"))
    assert urls and all(u.startswith(ALLOWED) for u in urls)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_bootstrap_runs_package_via_uv(script):
    text = script.read_text(encoding="utf-8")
    assert "uv run" in text and "-m freeagent" in text and "ExecutionPolicy" not in text


def test_install_sh_shellcheck_clean():
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    assert subprocess.run(["shellcheck", str(ROOT / "install.sh")]).returncode == 0
