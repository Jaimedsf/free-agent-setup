import pytest

from freeagent.detect import Gpu, best_gpu, detect_lang, detect_machine, parse_nvidia_smi, parse_rocm_smi
from freeagent.runner import RunResult
from tests.conftest import fixture


def test_parse_nvidia_one():
    [g] = parse_nvidia_smi(fixture("nvidia_smi_one.csv"))
    assert g == Gpu("nvidia", "NVIDIA GeForce RTX 3060 Ti", 8192, 7216)


def test_best_gpu_picks_most_free():
    gpus = parse_nvidia_smi(fixture("nvidia_smi_two.csv"))
    assert best_gpu(gpus).vram_free_mb == max(g.vram_free_mb for g in gpus) == 11000


def test_best_gpu_empty():
    assert best_gpu([]) is None


def test_parse_nvidia_garbage_is_empty():
    assert parse_nvidia_smi("NVIDIA-SMI has failed because it couldn't communicate\n") == []


def test_nvidia_smi_failure_means_no_gpu(fake_runner):
    fake_runner.set(("nvidia-smi",), RunResult(9, "", "NVML error"))
    m = detect_machine(fake_runner, which=lambda c: "/x/" + c if c == "nvidia-smi" else None)
    assert m.gpu is None


def test_detect_machine_uses_nvidia(fake_runner):
    fake_runner.set(("nvidia-smi",), RunResult(0, fixture("nvidia_smi_one.csv"), ""))
    m = detect_machine(fake_runner, which=lambda c: "/x/" + c if c == "nvidia-smi" else None)
    assert m.gpu.vram_free_mb == 7216 and m.cpu_cores >= 1 and m.ram_gb > 0


def test_parse_rocm():
    [g] = parse_rocm_smi(fixture("rocm_smi.json"))
    assert g.vendor == "amd" and g.vram_total_mb == 16368 and g.vram_free_mb == 16368 - 1024


@pytest.mark.parametrize(
    "env,cult,exp",
    [("pt_BR.UTF-8", None, "pt"), (None, "pt-BR", "pt"), ("en_US.UTF-8", None, "en"), (None, None, "en")],
)
def test_detect_lang(env, cult, exp):
    assert detect_lang(env, cult) == exp


def test_codex_logged_in_from_status(fake_runner):
    fake_runner.set(("codex", "login", "status"), RunResult(0, "Logged in using ChatGPT", ""))
    m = detect_machine(fake_runner, which=lambda c: "/x/codex" if c == "codex" else None)
    assert m.tools.codex and m.tools.codex_logged_in


def test_codex_present_not_logged_in(fake_runner):
    fake_runner.set(("codex", "login", "status"), RunResult(1, "Not logged in", ""))
    m = detect_machine(fake_runner, which=lambda c: "/x/codex" if c == "codex" else None)
    assert m.tools.codex and not m.tools.codex_logged_in


def test_other_agents_listed(fake_runner):
    m = detect_machine(fake_runner, which=lambda c: "/x/" + c if c in ("gemini", "agy") else None)
    assert m.tools.other_agents == ("gemini", "agy")
