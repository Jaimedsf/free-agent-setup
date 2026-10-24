from freeagent.auth import auth_codex, auth_nvidia, auth_ollama
from freeagent.runner import RunResult
from tests.conftest import machine


def _never(*_):
    raise AssertionError("must not prompt")


def test_nvidia_already_logged_in_no_prompt(fake_runner):
    fake_runner.set(("hermes", "auth", "status", "nvidia"), RunResult(0, "nvidia: logged in", ""))
    out = auth_nvidia(fake_runner, "en", ask=_never, open_url=_never)
    assert out.status == "ok"
    assert not any(c["args"][:3] == ["hermes", "auth", "add"] for c in fake_runner.calls)


def test_nvidia_declined_is_skipped(fake_runner):
    fake_runner.set(("hermes", "auth", "status"), RunResult(0, "nvidia: logged out", ""))
    assert auth_nvidia(fake_runner, "en", ask=lambda q: False, open_url=_never).status == "skipped"


def test_nvidia_runs_hermes_prompt_interactively(fake_runner):
    fake_runner.set(("hermes", "auth", "status"), RunResult(0, "nvidia: logged out", ""))
    fake_runner.set(("hermes", "auth", "add"), RunResult(0, "", ""))
    opened = []
    out = auth_nvidia(fake_runner, "en", ask=lambda q: True, open_url=opened.append)
    add = [c for c in fake_runner.calls if c["args"][:3] == ["hermes", "auth", "add"]][0]
    assert add["interactive"] is True and "--api-key" not in add["args"]
    assert add["args"] == ["hermes", "auth", "add", "nvidia", "--type", "api-key"]
    assert opened == ["https://build.nvidia.com/"] and out.status == "ok"


def test_failed_login_is_failed_not_exception(fake_runner):
    fake_runner.set(("hermes", "auth", "status"), RunResult(0, "nvidia: logged out", ""))
    fake_runner.set(("hermes", "auth", "add"), RunResult(1, "", "cancelled"))
    assert auth_nvidia(fake_runner, "en", ask=lambda q: True, open_url=lambda u: None).status == "failed"


def test_codex_not_offered_when_cli_absent(fake_runner):
    out = auth_codex(fake_runner, "en", machine(codex_logged_in=False), ask=_never)
    assert out.status == "skipped" and fake_runner.calls == []


def test_codex_adds_oauth_when_needed(fake_runner):
    fake_runner.set(("hermes", "auth", "status"), RunResult(0, "openai-codex: logged out", ""))
    fake_runner.set(("hermes", "auth", "add"), RunResult(0, "", ""))
    out = auth_codex(fake_runner, "en", machine(codex_logged_in=True), ask=lambda q: True)
    add = [c for c in fake_runner.calls if c["args"][:3] == ["hermes", "auth", "add"]][0]
    assert add["args"] == ["hermes", "auth", "add", "openai-codex", "--type", "oauth"] and out.status == "ok"


def test_ollama_signin_when_accepted(fake_runner):
    fake_runner.set(("ollama", "signin"), RunResult(0, "", ""))
    out = auth_ollama(fake_runner, "en", ask=lambda q: True, signed_in=lambda: False)
    assert out.status == "ok" and fake_runner.calls[0]["interactive"] is True


def test_ollama_already_signed_in(fake_runner):
    assert auth_ollama(fake_runner, "en", ask=_never, signed_in=lambda: True).status == "ok"
    assert fake_runner.calls == []
