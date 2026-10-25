"""Optional provider logins, always through the products' own commands.

Keys are typed by the person into the hidden prompt of `hermes auth add`; they never pass through this code.
"""

from collections.abc import Callable
from dataclasses import dataclass

from freeagent.detect import Machine
from freeagent.i18n import t
from freeagent.probe import OLLAMA_BASE, probe_openai
from freeagent.runner import Runner

NVIDIA_KEYS_URL = "https://build.nvidia.com/"
GEMINI_KEYS_URL = "https://aistudio.google.com/apikey"


@dataclass(frozen=True)
class AuthOutcome:
    provider: str
    status: str


def _logged_in(runner: Runner, provider: str) -> bool:
    r = runner.run(["hermes", "auth", "status", provider], timeout=60)
    return r.code == 0 and "logged in" in r.out.lower() and "logged out" not in r.out.lower()


def _add(runner: Runner, provider: str, kind: str) -> str:
    r = runner.run(["hermes", "auth", "add", provider, "--type", kind], timeout=900, interactive=True)
    return "ok" if r.code == 0 else "failed"


def _auth_api_key(runner: Runner, provider: str, keys_url: str, lang: str, ask: Callable[[str], bool],
                  open_url: Callable[[str], None]) -> AuthOutcome:
    if _logged_in(runner, provider):
        return AuthOutcome(provider, "ok")
    if not ask(t(f"auth.{provider}.ask", lang, url=keys_url)):
        return AuthOutcome(provider, "skipped")
    open_url(keys_url)
    return AuthOutcome(provider, _add(runner, provider, "api-key"))


def auth_nvidia(runner: Runner, lang: str, ask: Callable[[str], bool],
                open_url: Callable[[str], None]) -> AuthOutcome:
    return _auth_api_key(runner, "nvidia", NVIDIA_KEYS_URL, lang, ask, open_url)


def auth_gemini(runner: Runner, lang: str, ask: Callable[[str], bool],
                open_url: Callable[[str], None]) -> AuthOutcome:
    return _auth_api_key(runner, "gemini", GEMINI_KEYS_URL, lang, ask, open_url)


def _ollama_signed_in() -> bool:
    return probe_openai(OLLAMA_BASE + "/v1", "ollama", "nemotron-3-ultra:cloud", timeout=60).reason not in (
        "http_401", "http_403", "unreachable")


def auth_ollama(runner: Runner, lang: str, ask: Callable[[str], bool],
                signed_in: Callable[[], bool] = _ollama_signed_in) -> AuthOutcome:
    if signed_in():
        return AuthOutcome("ollama-cloud", "ok")
    if not ask(t("auth.ollama.ask", lang)):
        return AuthOutcome("ollama-cloud", "skipped")
    r = runner.run(["ollama", "signin"], timeout=900, interactive=True)
    return AuthOutcome("ollama-cloud", "ok" if r.code == 0 else "failed")


def auth_codex(runner: Runner, lang: str, m: Machine, ask: Callable[[str], bool]) -> AuthOutcome:
    if not m.tools.codex_logged_in:
        return AuthOutcome("openai-codex", "skipped")
    if _logged_in(runner, "openai-codex"):
        return AuthOutcome("openai-codex", "ok")
    if not ask(t("auth.codex.ask", lang)):
        return AuthOutcome("openai-codex", "skipped")
    return AuthOutcome("openai-codex", _add(runner, "openai-codex", "oauth"))
