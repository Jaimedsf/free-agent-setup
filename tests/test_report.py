from freeagent.catalog import load_catalog
from freeagent.plan import make_plan
from freeagent.policy import forbidden_words
from freeagent.probe import LocalResult, ProbeResult
from freeagent.report import render_report
from freeagent.select import select
from tests.conftest import machine


def _report(lang, warnings=()):
    m = machine(codex_logged_in=True)
    plan = make_plan(m, load_catalog())
    results = [(c, ProbeResult(c.id, c.kind == "nvidia", 1.0, "ok" if c.kind == "nvidia" else "http_402"))
               for c in plan.cloud]
    local = LocalResult("bonsai-2:9b", 65536, 100, 92.0)
    return render_report(lang, m, plan, results, local, select(plan, results, local), list(warnings))


def test_report_redacts_and_has_no_forbidden_words():
    secret = "nvapi" + "-ABCDEFGH1234"
    text = _report("en", [f"leaked {secret} here"])
    assert secret not in text
    assert not any(w in text.lower() for w in forbidden_words())


def test_report_pt_and_en_headings():
    assert "# free-agent-setup" in _report("en") and "Approved models" in _report("en")
    assert "Modelos aprovados" in _report("pt")


def test_report_lists_rejections_with_reason():
    text = _report("en")
    assert "http_402" in text and "nemotron" in text and "/model" in text and "--rollback" in text


def test_rollback_hint_uses_the_bootstrap_command():
    text = _report("en")                                  # test machine is linux
    assert "install.sh | bash -s -- --rollback" in text and "freeagent --rollback" not in text


def test_report_shows_alias_name_actually_written():
    m = machine(codex_logged_in=True)
    plan = make_plan(m, load_catalog())
    results = [(c, ProbeResult(c.id, c.id == "nvidia-nemotron-ultra", 1.0, "ok")) for c in plan.cloud]
    text = render_report("en", m, plan, results, None, select(plan, results, None), [],
                         alias_names={"nemotron": "nemotron-free"})
    assert "/model nemotron-free" in text
