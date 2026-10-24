from freeagent.i18n import load, t


def test_t_pt_and_fallback():
    assert t("plan.title", "pt") == "Plano de instalação"
    assert t("plan.title", "xx") == "Installation plan"
    assert t("missing.key", "pt") == "missing.key"


def test_t_format():
    assert t("probe.ok", "en", model="m", secs=1.5) == "m answered in 1.5s"


def test_en_pt_have_same_keys():
    assert set(load("en")) == set(load("pt"))
