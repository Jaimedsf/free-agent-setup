from dataclasses import dataclass, field

import pytest

from freeagent.runner import RunResult


@dataclass
class FakeRunner:
    """Answers commands by longest matching argument prefix and records every call."""

    responses: dict[tuple[str, ...], RunResult] = field(default_factory=dict)
    default: RunResult = RunResult(127, "", "not found")
    calls: list[dict] = field(default_factory=list)
    on_run: object = None  # optional callable(args) for side effects such as writing a log

    def set(self, prefix: tuple[str, ...], result: RunResult) -> None:
        self.responses[prefix] = result

    def run(self, args, *, timeout=60, input=None, env=None, interactive=False):
        self.calls.append({"args": list(args), "env": env, "interactive": interactive, "input": input})
        if self.on_run:
            self.on_run(list(args))
        best = None
        for prefix, result in self.responses.items():
            if tuple(args[: len(prefix)]) == prefix and (best is None or len(prefix) > len(best[0])):
                best = (prefix, result)
        return best[1] if best else self.default


@pytest.fixture
def fake_runner():
    return FakeRunner()


FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def machine(*, gpu="nvidia", gpu_free=7000, os="linux", lang="en", hermes=False, omh=False, ollama=False,
            codex=None, codex_logged_in=False):
    from freeagent.detect import Gpu, Machine, Tools

    g = None if gpu is None else Gpu(gpu, "Test GPU", 8192, gpu_free)
    tools = Tools(hermes=hermes, omh=omh, ollama=ollama, codex=codex_logged_in if codex is None else codex,
                  codex_logged_in=codex_logged_in)
    return Machine(os=os, gpu=g, ram_gb=32.0, cpu_cores=8, disk_free_gb=200.0, lang=lang, tools=tools)


@pytest.fixture(autouse=True)
def offline_catalog(monkeypatch):
    """Tests never download the online catalog; the default run falls back to the bundled one."""
    from freeagent import catalog

    def no_network(url):
        raise catalog.CatalogError("offline in tests")
    monkeypatch.setattr(catalog, "_fetch", no_network)
