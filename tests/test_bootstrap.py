import re
import shutil
import subprocess
import sys
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


def test_install_sh_reattaches_tty_for_prompts():
    # under `curl | bash` stdin is the exhausted pipe; prompts must read the terminal
    assert "</dev/tty" in (ROOT / "install.sh").read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("powershell"), reason="needs Windows PowerShell")
def test_install_ps1_under_iex_does_not_close_the_session():
    cmd = (f"$env:FREEAGENT_SRC='{ROOT}'; $env:FREEAGENT_ARGS='--dry-run --skip-cloud --skip-local --lang en'; "
           f"iex (Get-Content -Raw '{ROOT / 'install.ps1'}'); 'still-here'")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                         timeout=300).stdout
    assert "Installation plan" in out and "still-here" in out


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"),
                    reason="install.sh targets Linux; on Windows runners `bash` may be the absent WSL shim")
def test_install_sh_piped_without_terminal_still_runs():
    # `curl | bash` with no controlling terminal (CI, automation): /dev/tty exists but cannot be opened
    script = (ROOT / "install.sh").read_bytes()
    env = {**__import__("os").environ, "FREEAGENT_SRC": str(ROOT)}
    r = subprocess.run(["bash", "-s", "--", "--dry-run", "--skip-cloud", "--skip-local", "--lang", "en"],
                       input=script, capture_output=True, env=env, timeout=300)
    assert r.returncode == 0 and b"Installation plan" in r.stdout, r.stderr[-400:]
