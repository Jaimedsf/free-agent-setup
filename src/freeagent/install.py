"""Official installers and Hermes home resolution.

Verified against the upstream installers:
- Hermes install.sh accepts --skip-setup (install.ps1 takes -SkipSetup); both skip the interactive wizard.
- oh-my-hermes ships both install.ps1 and install.sh at the repository root.
- `hermes config path` prints the config file Hermes uses; its parent is the Hermes home.
  On native Windows that is %LOCALAPPDATA%\\hermes, not ~/.hermes.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from freeagent.detect import Machine
from freeagent.runner import Runner

HERMES_PS1 = "https://hermes-agent.nousresearch.com/install.ps1"
HERMES_SH = "https://hermes-agent.nousresearch.com/install.sh"
OMH_PS1 = "https://raw.githubusercontent.com/rlaope/oh-my-hermes/main/install.ps1"
OMH_SH = "https://raw.githubusercontent.com/rlaope/oh-my-hermes/main/install.sh"
OLLAMA_SH = "https://ollama.com/install.sh"
MARK = "# freeagent"

INSTALLERS: dict[tuple[str, str], list[str]] = {
    ("ollama", "windows"): ["winget", "install", "--id", "Ollama.Ollama", "-e",
                            "--accept-package-agreements", "--accept-source-agreements", "--silent"],
    ("ollama", "linux"): ["sh", "-c", f"curl -fsSL {OLLAMA_SH} | sh"],
    ("hermes", "windows"): ["powershell", "-NoProfile", "-Command",
                            f"& ([scriptblock]::Create((irm {HERMES_PS1}))) -SkipSetup"],
    ("hermes", "linux"): ["bash", "-c", f"curl -fsSL {HERMES_SH} | bash -s -- --skip-setup"],
    ("omh", "windows"): ["powershell", "-NoProfile", "-Command", f"irm {OMH_PS1} | iex"],
    ("omh", "linux"): ["bash", "-c", f"curl -fsSL {OMH_SH} | bash"],
}
_URLS = {
    ("ollama", "windows"): "winget:Ollama.Ollama",
    ("ollama", "linux"): OLLAMA_SH,
    ("hermes", "windows"): HERMES_PS1,
    ("hermes", "linux"): HERMES_SH,
    ("omh", "windows"): OMH_PS1,
    ("omh", "linux"): OMH_SH,
}


def installer_url(component: str, os: str) -> str:
    return _URLS[(component, os)]


def refresh_path() -> None:
    """Reload PATH from the registry so freshly installed tools are found (Windows only)."""
    try:
        import winreg
    except ImportError:
        return
    parts = []
    machine_env = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, machine_env), (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(hive, sub) as key:
                parts.append(os.path.expandvars(winreg.QueryValueEx(key, "Path")[0]))
        except OSError:
            continue
    if parts:
        os.environ["PATH"] = os.pathsep.join(parts + [os.environ.get("PATH", "")])


def ensure_installed(
    runner: Runner, m: Machine, components: list[str], *, refresh=refresh_path
) -> dict[str, str]:
    status = {}
    for component in components:
        r = runner.run(INSTALLERS[(component, m.os)], timeout=3600, interactive=True)
        status[component] = "ok" if r.code == 0 else f"failed:exit_{r.code}"
        refresh()
    return status


def resolve_hermes_home(runner: Runner, os: str, env: Mapping[str, str]) -> Path:
    current = env.get("HERMES_HOME")
    if current and (Path(current) / "config.yaml").is_file():
        return Path(current)
    clean = {k: v for k, v in env.items() if k != "HERMES_HOME"}
    r = runner.run(["hermes", "config", "path"], timeout=60, env=clean)
    if r.code == 0 and r.out.strip():
        return Path(r.out.strip().splitlines()[-1]).parent
    if os == "windows":
        return Path(env.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "hermes"
    return Path(env.get("HOME", str(Path.home()))) / ".hermes"


def persist_hermes_home(runner: Runner, os: str, home: Path, *, profile: Path | None = None) -> None:
    if os == "windows":
        runner.run(["powershell", "-NoProfile", "-Command",
                    f"[Environment]::SetEnvironmentVariable('HERMES_HOME', '{home}', 'User')"], timeout=60)
        return
    profile = profile or Path.home() / ".profile"
    lines = profile.read_text(encoding="utf-8").splitlines() if profile.exists() else []
    lines = [ln for ln in lines if not ln.endswith(MARK)]
    lines.append(f'export HERMES_HOME="{home.as_posix()}"  {MARK}')
    profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
