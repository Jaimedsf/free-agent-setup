import json
import os
import platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from freeagent.runner import Runner

OTHER_AGENTS = ("gemini", "agy", "cursor-agent", "opencode")


@dataclass(frozen=True)
class Gpu:
    vendor: str
    name: str
    vram_total_mb: int
    vram_free_mb: int


@dataclass(frozen=True)
class Tools:
    hermes: bool = False
    omh: bool = False
    ollama: bool = False
    codex: bool = False
    codex_logged_in: bool = False
    other_agents: tuple[str, ...] = ()


@dataclass(frozen=True)
class Machine:
    os: str
    gpu: Gpu | None
    ram_gb: float
    cpu_cores: int
    disk_free_gb: float
    lang: str
    tools: Tools


def parse_nvidia_smi(text: str) -> list[Gpu]:
    gpus = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            gpus.append(Gpu("nvidia", parts[0], int(float(parts[1])), int(float(parts[2]))))
        except ValueError:
            continue
    return gpus


def parse_rocm_smi(text: str) -> list[Gpu]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    gpus = []
    for card in data.values() if isinstance(data, dict) else []:
        if not isinstance(card, dict):
            continue
        try:
            total = int(card["VRAM Total Memory (B)"]) // 1048576
            used = int(card.get("VRAM Total Used Memory (B)", 0)) // 1048576
        except (KeyError, ValueError):
            continue
        name = card.get("Card Series") or card.get("Card series") or "AMD GPU"
        gpus.append(Gpu("amd", name, total, total - used))
    return gpus


def best_gpu(gpus: list[Gpu]) -> Gpu | None:
    return max(gpus, key=lambda g: g.vram_free_mb, default=None)


def detect_lang(lang_env: str | None, culture: str | None) -> str:
    for value in (lang_env, culture):
        if value:
            return "pt" if value.lower().startswith("pt") else "en"
    return "en"


def _ram_gb(os_name: str) -> float:
    try:
        if os_name == "windows":
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong)
                    for n in ("total", "avail", "tpage", "apage", "tvirt", "avirt", "aext")
                ]

            st = MemStatus()
            st.dwLength = ctypes.sizeof(st)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.total / 1024**3
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024**2
    except Exception:
        pass
    return 0.0


def _gpu(runner: Runner, which: Callable[[str], str | None]) -> Gpu | None:
    if which("ollama"):
        # A previous run leaves our local model loaded; measure VRAM without it.
        runner.run(["ollama", "stop", "freeagent-local"], timeout=30)
    if which("nvidia-smi"):
        r = runner.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                        "--format=csv,noheader,nounits"], timeout=20)
        if r.code == 0:
            gpu = best_gpu(parse_nvidia_smi(r.out))
            if gpu:
                return gpu
    if which("rocm-smi"):
        r = runner.run(["rocm-smi", "--showmeminfo", "vram", "--showproductname", "--json"], timeout=20)
        if r.code == 0:
            return best_gpu(parse_rocm_smi(r.out))
    return None


def _tools(runner: Runner, which: Callable[[str], str | None]) -> Tools:
    codex = bool(which("codex"))
    logged = codex and runner.run(["codex", "login", "status"], timeout=20).code == 0
    return Tools(
        hermes=bool(which("hermes")),
        omh=bool(which("omh")),
        ollama=bool(which("ollama")),
        codex=codex,
        codex_logged_in=logged,
        other_agents=tuple(a for a in OTHER_AGENTS if which(a)),
    )


def detect_machine(runner: Runner, which: Callable[[str], str | None] = shutil.which) -> Machine:
    os_name = "windows" if platform.system() == "Windows" else "linux"
    culture = None
    if os_name == "windows" and not os.environ.get("LANG"):
        r = runner.run(["powershell", "-NoProfile", "-Command", "(Get-Culture).Name"], timeout=20)
        culture = r.out.strip() if r.code == 0 else None
    try:
        disk = shutil.disk_usage(Path.home()).free / 1024**3
    except OSError:
        disk = 0.0
    return Machine(
        os=os_name,
        gpu=_gpu(runner, which),
        ram_gb=round(_ram_gb(os_name), 1),
        cpu_cores=os.cpu_count() or 1,
        disk_free_gb=round(disk, 1),
        lang=detect_lang(os.environ.get("LANG"), culture),
        tools=_tools(runner, which),
    )
