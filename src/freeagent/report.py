from freeagent.catalog import CloudCandidate
from freeagent.detect import Machine
from freeagent.hermes_config import Selection
from freeagent.i18n import t
from freeagent.plan import Plan
from freeagent.probe import LocalResult, ProbeResult
from freeagent.redact import redact


def render_report(lang: str, machine: Machine, plan: Plan, results: list[tuple[CloudCandidate, ProbeResult]],
                  local: LocalResult | None, selection: Selection | None, warnings: list[str]) -> str:
    g = machine.gpu
    gpu = f"{g.name} ({g.vram_free_mb}/{g.vram_total_mb} MB)" if g else t("report.no_gpu", lang)
    lines = [
        "# free-agent-setup",
        "",
        f"## {t('report.machine', lang)}",
        f"- OS: {machine.os} · RAM: {machine.ram_gb} GB · CPU: {machine.cpu_cores} · GPU: {gpu}",
        "",
        f"## {t('report.local', lang)}",
    ]
    if local:
        lines.append(f"- `{local.model}` · ctx {local.ctx} · {local.gpu_pct}% GPU · {local.tok_s} tok/s")
    else:
        lines.append(f"- {t('report.no_local', lang)}")
    lines += ["", f"## {t('report.approved', lang)}"]
    for c, r in results:
        if r.ok:
            lines.append(f"- `/model {c.alias}` → `{c.model}` ({r.latency_s}s)")
    lines += ["", f"## {t('report.rejected', lang)}"]
    for c, r in results:
        if not r.ok:
            lines.append(f"- `{c.model}`: {r.reason}")
    if selection:
        lines += ["", f"## {t('report.config', lang)}",
                  f"- {t('report.main', lang)}: `{selection.main.model}`",
                  f"- {t('report.fallbacks', lang)}: "
                  + (", ".join(f"`{f.model}`" for f in selection.fallbacks) or "-"),
                  f"- {t('report.executor', lang)}: `{plan.executor}`"]
    if warnings or plan.notes:
        lines += ["", f"## {t('report.warnings', lang)}"]
        lines += [f"- {t(n, lang)}" for n in plan.notes] + [f"- {w}" for w in warnings]
    lines += ["", f"## {t('report.next', lang)}", f"- {t('report.howto_model', lang)}",
              f"- {t('report.howto_rollback', lang)}", ""]
    return redact("\n".join(lines))
