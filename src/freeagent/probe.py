"""Real, minimal requests that decide which models enter the configuration."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from freeagent.catalog import LocalTier
from freeagent.runner import Runner

OLLAMA_BASE = "http://127.0.0.1:11434"
LOCAL_NAME = "freeagent-local"
MIN_CTX = 16384
PROMPT = "Reply only: OK"
_SERVED = re.compile(r"API call #1: model=(\S+) provider=(\S+)")
_GPU = re.compile(r"(?:(\d+)%/(\d+)% CPU/GPU|(\d+)% GPU|(\d+)% CPU)")


@dataclass(frozen=True)
class ProbeResult:
    id: str
    ok: bool
    latency_s: float | None
    reason: str


@dataclass(frozen=True)
class LocalResult:
    model: str
    ctx: int
    gpu_pct: int
    tok_s: float


def parse_ollama_ps(text: str) -> dict[str, int]:
    out = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        m = _GPU.search(line)
        if not parts or not m:
            continue
        out[parts[0]] = int(m.group(2) or m.group(3) or 0)  # "100% CPU" -> 0
    return out


def last_served(log_text: str, session_hint: str | None = None) -> tuple[str, str] | None:
    found = None
    for line in log_text.splitlines():
        if session_hint and session_hint not in line:
            continue
        m = _SERVED.search(line)
        if m:
            found = (m.group(2), m.group(1))
    return found


def _post_json(url: str, body: dict, timeout: float, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def probe_openai(base_url: str, api_key: str, model: str, timeout: float = 90) -> ProbeResult:
    body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 300}
    start = time.monotonic()
    try:
        data = _post_json(base_url.rstrip("/") + "/chat/completions", body, timeout,
                          {"Authorization": f"Bearer {api_key}"})
    except urllib.error.HTTPError as e:
        return ProbeResult(model, False, None, f"http_{e.code}")
    except TimeoutError:
        return ProbeResult(model, False, None, "timeout")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return ProbeResult(model, False, None, "timeout" if "timed out" in str(e) else "unreachable")
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        return ProbeResult(model, False, None, "empty")
    return ProbeResult(model, True, round(time.monotonic() - start, 1), "ok")


def probe_via_hermes(runner: Runner, hermes_home: Path, alias: str, expect_model: str) -> ProbeResult:
    """Ask Hermes itself through an alias; only counts if the expected model served it (not a fallback)."""
    log = hermes_home / "logs" / "agent.log"
    offset = log.stat().st_size if log.exists() else 0
    env = {**os.environ, "HERMES_HOME": str(hermes_home)}
    start = time.monotonic()
    r = runner.run(["hermes", "chat", "--oneshot", "-m", alias, "-q", PROMPT], timeout=180, env=env)
    latency = round(time.monotonic() - start, 1)
    new = ""
    if log.exists():
        with open(log, "rb") as f:
            f.seek(offset)
            new = f.read().decode("utf-8", "replace")
    served = last_served(new)
    if served is None:
        return ProbeResult(alias, False, None, f"no_response_exit_{r.code}")
    if served[1] != expect_model:
        return ProbeResult(alias, False, None, "served_by_other")
    return ProbeResult(alias, True, latency, "ok")


def _spawn(os_name: str) -> None:
    exe = shutil.which("ollama")
    flags = {"creationflags": 0x00000008} if os_name == "windows" else {"start_new_session": True}
    if os_name == "windows" and exe:
        app = Path(exe).with_name("ollama app.exe")
        args = [str(app)] if app.exists() else [exe, "serve"]
    else:
        args = [exe or "ollama", "serve"]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)


def _up(base: str) -> bool:
    try:
        with urllib.request.urlopen(base + "/api/version", timeout=2):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def ensure_ollama_running(runner: Runner, os: str, wait_s: int = 30, *, base: str = OLLAMA_BASE,
                          spawn=_spawn) -> bool:
    if _up(base):
        return True
    try:
        spawn(os)
    except OSError:
        return False
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if _up(base):
            return True
        time.sleep(0.5)
    return False


def _try_ctx(runner: Runner, model: str, ctx: int, http_post, base: str) -> LocalResult | None:
    with tempfile.TemporaryDirectory() as d:
        mf = Path(d) / "Modelfile"
        mf.write_text(f"FROM {model}\nPARAMETER num_ctx {ctx}\n", encoding="utf-8")
        if runner.run(["ollama", "create", LOCAL_NAME, "-f", str(mf)], timeout=600).code != 0:
            return None
    try:
        data = http_post(base + "/api/generate", {
            "model": LOCAL_NAME, "prompt": PROMPT, "stream": False, "think": False,
            "options": {"num_predict": 200},
        }, 300)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    tok_s = data.get("eval_count", 0) / (data.get("eval_duration", 1) / 1e9 or 1)
    ps = parse_ollama_ps(runner.run(["ollama", "ps"], timeout=30).out)
    pct = next((v for k, v in ps.items() if k.split(":")[0] == LOCAL_NAME), 0)
    return LocalResult(model, ctx, pct, round(tok_s, 1))


def fit_local(runner: Runner, tier_chain: list[LocalTier], *, base: str = OLLAMA_BASE,
              http_post=_post_json) -> LocalResult | None:
    for tier in tier_chain:
        if runner.run(["ollama", "pull", tier.model], timeout=3600).code != 0:
            continue
        ctx = tier.ctx
        while ctx >= MIN_CTX:
            result = _try_ctx(runner, tier.model, ctx, http_post, base)
            if result and result.gpu_pct == 100:
                return result
            ctx //= 2
    return None
