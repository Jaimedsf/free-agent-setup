import os
import sys

import pytest

from freeagent.runner import SubprocessRunner


@pytest.mark.skipif(sys.platform != "win32", reason=".cmd shims are a Windows thing")
def test_runs_cmd_shim_by_bare_name(tmp_path, monkeypatch):
    (tmp_path / "fakeomh.cmd").write_text("@echo off\r\necho shim-ok %1\r\n")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    r = SubprocessRunner().run(["fakeomh", "hello"])
    assert r.code == 0 and "shim-ok hello" in r.out


def test_missing_command_is_127():
    assert SubprocessRunner().run(["definitely-not-a-command-xyz"]).code == 127
