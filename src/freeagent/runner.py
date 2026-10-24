import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RunResult:
    code: int
    out: str
    err: str


class Runner(Protocol):
    def run(
        self,
        args: list[str],
        *,
        timeout: float = 60,
        input: str | None = None,
        env: dict | None = None,
        interactive: bool = False,
    ) -> RunResult: ...


class SubprocessRunner:
    """Runs real commands. Interactive commands inherit the terminal so prompts reach the person."""

    def run(self, args, *, timeout=60, input=None, env=None, interactive=False):
        try:
            if interactive:
                proc = subprocess.run(args, env=env, timeout=timeout)
                return RunResult(proc.returncode, "", "")
            proc = subprocess.run(
                args, input=input, env=env, timeout=timeout, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")
        except FileNotFoundError as e:
            return RunResult(127, "", str(e))
        except subprocess.TimeoutExpired:
            return RunResult(124, "", "timeout")
