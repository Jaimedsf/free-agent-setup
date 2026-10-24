from dataclasses import dataclass, field

import pytest

from freeagent.runner import RunResult


@dataclass
class FakeRunner:
    """Answers commands by longest matching argument prefix and records every call."""

    responses: dict[tuple[str, ...], RunResult] = field(default_factory=dict)
    default: RunResult = RunResult(127, "", "not found")
    calls: list[dict] = field(default_factory=list)

    def set(self, prefix: tuple[str, ...], result: RunResult) -> None:
        self.responses[prefix] = result

    def run(self, args, *, timeout=60, input=None, env=None, interactive=False):
        self.calls.append({"args": list(args), "env": env, "interactive": interactive, "input": input})
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
