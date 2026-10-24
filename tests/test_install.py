from pathlib import Path

from freeagent.install import (
    INSTALLERS,
    ensure_installed,
    installer_url,
    persist_hermes_home,
    resolve_hermes_home,
)
from freeagent.runner import RunResult
from tests.conftest import machine

OFFICIAL = ("https://ollama.com/", "https://hermes-agent.nousresearch.com/",
            "https://raw.githubusercontent.com/rlaope/oh-my-hermes/", "winget:")


def test_installer_urls_are_https_official():
    for (component, os_name) in INSTALLERS:
        assert installer_url(component, os_name).startswith(OFFICIAL)


def test_hermes_installers_skip_wizard():
    assert "-SkipSetup" in " ".join(INSTALLERS[("hermes", "windows")])
    assert "--skip-setup" in " ".join(INSTALLERS[("hermes", "linux")])


def test_resolve_prefers_valid_env(fake_runner, tmp_path):
    (tmp_path / "config.yaml").write_text("x: 1\n")
    assert resolve_hermes_home(fake_runner, "linux", {"HERMES_HOME": str(tmp_path)}) == tmp_path


def test_resolve_ignores_env_without_config(fake_runner, tmp_path):
    home = resolve_hermes_home(fake_runner, "linux", {"HERMES_HOME": str(tmp_path), "HOME": "/h"})
    assert home == Path("/h") / ".hermes"


def test_resolve_asks_hermes_without_inherited_env(fake_runner, tmp_path):
    fake_runner.set(("hermes", "config", "path"), RunResult(0, str(tmp_path / "config.yaml") + "\n", ""))
    home = resolve_hermes_home(fake_runner, "windows", {"HERMES_HOME": "/nope", "LOCALAPPDATA": "/l"})
    assert home == tmp_path
    assert "HERMES_HOME" not in fake_runner.calls[0]["env"]


def test_resolve_windows_default(fake_runner):
    assert resolve_hermes_home(fake_runner, "windows", {"LOCALAPPDATA": "/l"}) == Path("/l") / "hermes"


def test_persist_linux_idempotent(fake_runner, tmp_path):
    profile = tmp_path / ".profile"
    profile.write_text("export A=1\n")
    persist_hermes_home(fake_runner, "linux", Path("/x/hermes"), profile=profile)
    persist_hermes_home(fake_runner, "linux", Path("/x/hermes"), profile=profile)
    lines = profile.read_text().splitlines()
    assert lines.count('export HERMES_HOME="/x/hermes"  # freeagent') == 1 and lines[0] == "export A=1"


def test_persist_windows_uses_user_env(fake_runner):
    fake_runner.default = RunResult(0, "", "")
    persist_hermes_home(fake_runner, "windows", Path("C:/h"))
    assert "SetEnvironmentVariable('HERMES_HOME'" in fake_runner.calls[0]["args"][-1]


def test_ensure_installed_reports_failure(fake_runner):
    fake_runner.default = RunResult(1, "", "boom")
    assert ensure_installed(fake_runner, machine(), ["omh"]) == {"omh": "failed:exit_1"}


def test_ensure_installed_ok(fake_runner):
    fake_runner.default = RunResult(0, "", "")
    assert ensure_installed(fake_runner, machine(), ["hermes"], refresh=lambda: None) == {"hermes": "ok"}
    assert fake_runner.calls[0]["interactive"] is True
