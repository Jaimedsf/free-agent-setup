import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from freeagent.catalog import LocalTier
from freeagent.probe import (
    ensure_ollama_running,
    fit_local,
    last_served,
    parse_ollama_ps,
    probe_openai,
    probe_via_hermes,
)
from freeagent.runner import RunResult
from tests.conftest import fixture

NEMO = "nvidia/nemotron-3-ultra-550b-a55b"
LOG_LINE = ("2026-01-01 00:00:00,000 INFO [local-0] agent.conversation_loop: API call #1: "
            "model={model} provider={provider} in=1 out=1 total=2 latency=1.0s\n")


def tier(model="bonsai-2:9b", ctx=65536):
    return LocalTier(6144, 10239, model, 3.2, ctx)


def test_parse_ollama_ps():
    assert parse_ollama_ps(fixture("ollama_ps_full_gpu.txt"))["bonsai-2:9b"] == 100
    assert parse_ollama_ps(fixture("ollama_ps_split.txt"))["qwen2.5-coder:7b"] == 91


def test_parse_ollama_ps_cpu_only():
    text = "NAME ID SIZE PROCESSOR CONTEXT UNTIL\nm:1 abc 1 GB 100% CPU 4096 llamacpp now\n"
    assert parse_ollama_ps(text)["m:1"] == 0


def test_last_served():
    assert last_served(fixture("agent_log_tail.txt")) == ("nvidia", NEMO)


def test_last_served_none():
    assert last_served("nothing here\n") is None


@pytest.fixture
def hermes_home(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "agent.log").write_text(LOG_LINE.format(model=NEMO, provider="nvidia"))
    return tmp_path


def _logging_runner(fake_runner, home, model, provider):
    def write(args):
        with open(home / "logs" / "agent.log", "a") as f:
            f.write(LOG_LINE.format(model=model, provider=provider))
    fake_runner.default = RunResult(0, "OK", "")
    fake_runner.on_run = write
    return fake_runner


def test_probe_via_hermes_accepts_expected_model(fake_runner, hermes_home):
    runner = _logging_runner(fake_runner, hermes_home, NEMO, "nvidia")
    r = probe_via_hermes(runner, hermes_home, "nemotron", NEMO)
    assert r.ok and fake_runner.calls[0]["args"][:5] == ["hermes", "chat", "--oneshot", "-m", "nemotron"]
    assert fake_runner.calls[0]["env"]["HERMES_HOME"] == str(hermes_home)


def test_probe_via_hermes_rejects_fallback(fake_runner, hermes_home):
    runner = _logging_runner(fake_runner, hermes_home, "gpt-5.6-terra", "openai-codex")
    r = probe_via_hermes(runner, hermes_home, "nemotron", NEMO)
    assert not r.ok and r.reason == "served_by_other"


def test_probe_via_hermes_ignores_old_log_lines(fake_runner, hermes_home):
    fake_runner.default = RunResult(1, "", "boom")          # nothing new logged; old line must not count
    r = probe_via_hermes(fake_runner, hermes_home, "nemotron", NEMO)
    assert not r.ok


def _serve(status, body):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/v1"


def test_probe_openai_ok():
    srv, url = _serve(200, {"choices": [{"message": {"content": "OK"}}]})
    try:
        r = probe_openai(url, "x", "m")
        assert r.ok and r.latency_s is not None
    finally:
        srv.shutdown()


def test_probe_openai_maps_402():
    srv, url = _serve(402, {"error": {"message": "not in the Free plan"}})
    try:
        assert probe_openai(url, "x", "m").reason == "http_402"
    finally:
        srv.shutdown()


def test_probe_openai_empty_content_fails():
    srv, url = _serve(200, {"choices": [{"message": {"content": ""}}]})
    try:
        assert probe_openai(url, "x", "m").reason == "empty"
    finally:
        srv.shutdown()


class FakeOllama:
    """ollama CLI + /api/generate double. gpu_by_ctx maps num_ctx -> GPU % reported by `ollama ps`."""

    def __init__(self, fake_runner, gpu_by_ctx):
        self.runner, self.gpu_by_ctx, self.ctx = fake_runner, gpu_by_ctx, None
        fake_runner.default = RunResult(0, "", "")
        fake_runner.on_run = self._on_run

    def _on_run(self, args):
        if args[:2] == ["ollama", "create"]:
            text = open(args[args.index("-f") + 1]).read()
            self.ctx = int(text.split("num_ctx")[1].split()[0])
            pct = self.gpu_by_ctx(self.ctx)
            proc = "100% GPU" if pct == 100 else f"{100 - pct}%/{pct}% CPU/GPU"
            self.runner.set(("ollama", "ps"), RunResult(0, f"NAME ID SIZE PROCESSOR\nfreeagent-local:latest x 1 GB {proc} 1 llamacpp now\n", ""))

    def post(self, url, body, timeout):
        return {"eval_count": 100, "eval_duration": 1_000_000_000}


def test_fit_local_halves_ctx_then_succeeds(fake_runner):
    fo = FakeOllama(fake_runner, lambda ctx: 100 if ctx <= 32768 else 91)
    r = fit_local(fake_runner, [tier(ctx=65536)], http_post=fo.post)
    assert r.ctx == 32768 and r.gpu_pct == 100 and r.tok_s == 100.0 and r.model == "bonsai-2:9b"


def test_fit_local_descends_tier(fake_runner):
    fo = FakeOllama(fake_runner, lambda ctx: 100 if fo_model[0] == "bonsai-2:4b" else 50)
    fo_model = [None]
    orig = fake_runner.on_run

    def track(args):
        if args[:2] == ["ollama", "pull"]:
            fo_model[0] = args[2]
        orig(args)
    fake_runner.on_run = track
    r = fit_local(fake_runner, [tier(ctx=32768), tier("bonsai-2:4b", 32768)], http_post=fo.post)
    assert r.model == "bonsai-2:4b"


def test_fit_local_gives_up(fake_runner):
    fo = FakeOllama(fake_runner, lambda ctx: 50)
    assert fit_local(fake_runner, [tier(ctx=32768)], http_post=fo.post) is None


def test_ollama_not_running_times_out(fake_runner):
    spawned = []
    ok = ensure_ollama_running(fake_runner, "linux", wait_s=1, base="http://127.0.0.1:9",
                               spawn=lambda os_name: spawned.append(os_name))
    assert ok is False and spawned == ["linux"]
