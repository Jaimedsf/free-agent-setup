from datetime import datetime

from freeagent.__main__ import configure_and_check, main
from freeagent.hermes_config import Approved, Selection
from freeagent.runner import RunResult
from tests.conftest import machine

A = Approved("nemotron", "nvidia", "nvidia/nemotron-3-ultra-550b-a55b", tier="heavy")
SEL = Selection(main=A, fallbacks=[], local=None, compression=A, aliases=[A])


def test_main_dry_run_writes_nothing(fake_runner, tmp_path, capsys):
    code = main(["--dry-run", "--lang", "en", "--hermes-home", str(tmp_path)], runner=fake_runner,
                detect=lambda r: machine(gpu_free=7000))
    assert code == 0 and fake_runner.calls == [] and list(tmp_path.iterdir()) == []
    out = capsys.readouterr().out
    assert "Installation plan" in out and "bonsai-2:9b" in out
    assert "Model catalog: bundled" in out and "offline in tests" in out


def test_main_explicit_catalog_failure_is_fatal(fake_runner, tmp_path, capsys):
    code = main(["--dry-run", "--lang", "en", "--catalog", str(tmp_path / "nope.json")], runner=fake_runner,
                detect=lambda r: machine())
    assert code == 3 and "Could not use the catalog" in capsys.readouterr().out


def test_main_restores_on_failed_check(fake_runner, tmp_path):
    hh, oh = tmp_path / "h", tmp_path / "o"
    hh.mkdir()
    oh.mkdir()
    (hh / "config.yaml").write_text("model:\n  default: old\n")
    fake_runner.set(("hermes", "config", "check"), RunResult(1, "", "formatting error"))
    ok = configure_and_check(fake_runner, hh, oh, SEL, datetime(2026, 1, 1))
    assert ok is None and (hh / "config.yaml").read_text() == "model:\n  default: old\n"


def test_configure_ok_keeps_change(fake_runner, tmp_path):
    hh, oh = tmp_path / "h", tmp_path / "o"
    hh.mkdir()
    oh.mkdir()
    (hh / "config.yaml").write_text("model:\n  default: old\n")
    fake_runner.set(("hermes", "config", "check"), RunResult(0, "Config version: 51", ""))
    assert configure_and_check(fake_runner, hh, oh, SEL, datetime(2026, 1, 1)) == {"nemotron": "nemotron"}
    assert "nemotron-3-ultra" in (hh / "config.yaml").read_text()


def test_main_rollback_without_backup_returns_1(fake_runner, tmp_path):
    assert main(["--rollback", "--hermes-home", str(tmp_path), "--omh-home", str(tmp_path)],
                runner=fake_runner, detect=lambda r: machine()) == 1


def test_main_cancel_returns_1(fake_runner, tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    assert main(["--lang", "en", "--hermes-home", str(tmp_path)], runner=fake_runner,
                detect=lambda r: machine()) == 1
    assert fake_runner.calls == []


def test_configure_without_own_backup_restores_earlier_one(fake_runner, tmp_path):
    from freeagent.backup import make_backup
    hh, oh = tmp_path / "h", tmp_path / "o"
    hh.mkdir()
    oh.mkdir()
    (hh / "config.yaml").write_text("model:\n  default: original\n")
    make_backup(hh, oh, datetime(2026, 1, 1))
    (hh / "config.yaml").write_text("model:\n  default: provisional\n")   # e.g. aliases written for probes
    fake_runner.set(("hermes", "config", "check"), RunResult(1, "", ""))
    assert configure_and_check(fake_runner, hh, oh, SEL, datetime(2026, 1, 2), backup=False) is None
    assert (hh / "config.yaml").read_text() == "model:\n  default: original\n"


def test_output_is_utf8_even_on_legacy_console():
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    out = subprocess.run([sys.executable, "-m", "freeagent", "--dry-run", "--lang", "pt", "--skip-cloud"],
                         capture_output=True, env=env, timeout=120).stdout
    assert "Plano de instalação" in out.decode("utf-8")


def test_main_refreshes_path_before_detecting(fake_runner, tmp_path):
    order = []
    main(["--dry-run", "--hermes-home", str(tmp_path)], runner=fake_runner,
         detect=lambda r: order.append("detect") or machine(), refresh=lambda: order.append("refresh"))
    assert order == ["refresh", "detect"]


def test_ask_treats_eof_as_no(monkeypatch, capsys):
    from freeagent.__main__ import _ask

    def eof(*_):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert _ask(False)("Proceed?") is False
    assert "--yes" in capsys.readouterr().out


def test_failed_probes_leave_config_as_it_was(fake_runner, tmp_path, monkeypatch):
    hh, oh = tmp_path / "h", tmp_path / "o"
    hh.mkdir()
    oh.mkdir()
    original = "model:\n  default: mine\nmodel_aliases:\n  keep:\n    model: x\n    provider: custom\n"
    (hh / "config.yaml").write_text(original)
    monkeypatch.setattr("freeagent.__main__.ensure_ollama_running", lambda *a, **k: False)
    fake_runner.set(("hermes", "auth", "status"), RunResult(0, "nvidia: logged in\nopenai-codex: logged in", ""))
    fake_runner.default = RunResult(1, "", "no answer")       # every probe through Hermes fails
    code = main(["--yes", "--lang", "en", "--skip-local", "--hermes-home", str(hh), "--omh-home", str(oh)],
                runner=fake_runner, detect=lambda r: machine(hermes=True, omh=True, ollama=True,
                                                             codex_logged_in=True),
                refresh=lambda: None)
    assert code == 3 and (hh / "config.yaml").read_text() == original
