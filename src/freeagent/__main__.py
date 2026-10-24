"""freeagent: detect → plan → confirm → install → auth → probe → configure → report."""

import argparse
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from freeagent.auth import auth_codex, auth_nvidia, auth_ollama
from freeagent.backup import make_backup, restore_latest
from freeagent.catalog import load_catalog
from freeagent.detect import Machine, detect_machine
from freeagent.hermes_config import ConfigError, Selection, apply_selection, write_aliases
from freeagent.i18n import t
from freeagent.install import (
    ensure_installed,
    installer_url,
    persist_hermes_home,
    refresh_path,
    resolve_hermes_home,
)
from freeagent.omh_routing import apply_omh, hermes_chains, maestro_chains
from freeagent.plan import Plan, make_plan
from freeagent.probe import (
    OLLAMA_BASE,
    ensure_ollama_running,
    fit_local,
    probe_openai,
    probe_via_hermes,
)
from freeagent.report import render_report
from freeagent.runner import Runner, SubprocessRunner
from freeagent.select import approved_from, select

EXIT_OK, EXIT_CANCELLED, EXIT_CONFIG, EXIT_FATAL = 0, 1, 2, 3
STATE = "freeagent-state.json"
REPORT = "freeagent-report.md"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="freeagent")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--lang", choices=("pt", "en"))
    p.add_argument("--skip-local", action="store_true")
    p.add_argument("--skip-cloud", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--hermes-home", type=Path, help="explicit Hermes home (not persisted)")
    p.add_argument("--omh-home", type=Path, help="explicit oh-my-hermes home")
    return p.parse_args(argv)


def plan_lines(m: Machine, plan: Plan, lang: str) -> list[str]:
    g = m.gpu
    lines = [t("plan.title", lang), ""]
    lines.append(t("plan.machine", lang, os=m.os, ram=m.ram_gb, cpu=m.cpu_cores,
                   gpu=f"{g.name} {g.vram_free_mb}/{g.vram_total_mb} MB" if g else t("report.no_gpu", lang)))
    if plan.local:
        lines.append(t("plan.local", lang, model=plan.local.model, size=plan.local.download_gb, ctx=plan.local.ctx))
    for note in plan.notes:
        lines.append("  " + t(note, lang))
    for c in plan.cloud:
        lines.append(t("plan.cloud", lang, model=c.model, kind=c.kind))
    for comp in plan.install:
        lines.append(t("plan.install", lang, name=comp, url=installer_url(comp, m.os)))
    lines.append(t("plan.executor", lang, executor=plan.executor))
    if m.tools.other_agents:
        lines.append(t("plan.other_agents", lang, names=", ".join(m.tools.other_agents)))
    return lines


def configure_and_check(runner: Runner, hermes_home: Path, omh_home: Path, sel: Selection,
                        now: datetime, *, backup: bool = True) -> bool:
    """Backup, write, validate with Hermes itself; restore the latest backup if validation fails.

    Pass backup=False when the caller already took the pre-run backup (so a failure restores that one).
    """
    if backup:
        make_backup(hermes_home, omh_home, now)
    try:
        apply_selection(hermes_home / "config.yaml", sel, hermes_home / STATE)
    except ConfigError:
        restore_latest(hermes_home, omh_home)
        return False
    env = {**os.environ, "HERMES_HOME": str(hermes_home)}
    r = runner.run(["hermes", "config", "check"], timeout=120, env=env)
    if r.code != 0 or "formatting error" in (r.out + r.err).lower():
        restore_latest(hermes_home, omh_home)
        return False
    return True


def _ask(yes: bool):
    def ask(question: str) -> bool:
        if yes:
            print(question + " [Y]")
            return True
        return input(question + " [y/N] ").strip().lower() in ("y", "s", "yes", "sim")
    return ask


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None, runner: Runner | None = None, *, detect=detect_machine,
         refresh=refresh_path) -> int:
    _utf8_console()
    args = parse_args(argv)
    refresh()  # tools installed earlier in this session are not on the inherited PATH yet
    runner = runner or SubprocessRunner()
    omh_home = args.omh_home or Path.home() / ".omh"

    if args.rollback:
        home = args.hermes_home or resolve_hermes_home(runner, detect(runner).os, os.environ)
        restored = restore_latest(home, omh_home)
        print(t("rollback.done" if restored else "rollback.none", args.lang or "en", path=restored))
        return EXIT_OK if restored else EXIT_CANCELLED

    m = detect(runner)
    lang = args.lang or m.lang
    cat = load_catalog()
    plan = make_plan(m, cat, skip_local=args.skip_local, skip_cloud=args.skip_cloud)
    print("\n".join(plan_lines(m, plan, lang)))
    if args.dry_run:
        return EXIT_OK
    ask = _ask(args.yes)
    if not ask(t("confirm.proceed", lang)):
        return EXIT_CANCELLED

    warnings: list[str] = []
    status = ensure_installed(runner, m, plan.install)
    for comp, st in status.items():
        if st != "ok":
            warnings.append(f"install {comp}: {st}")
    if status.get("hermes", "ok") != "ok":
        print(t("fatal.hermes", lang))
        return EXIT_FATAL

    home = args.hermes_home or resolve_hermes_home(runner, m.os, os.environ)
    if not args.hermes_home:
        persist_hermes_home(runner, m.os, home)
    os.environ["HERMES_HOME"] = str(home)
    home.mkdir(parents=True, exist_ok=True)
    if not (home / "config.yaml").exists():
        (home / "config.yaml").write_text("{}\n", encoding="utf-8")

    kinds = {c.kind for c in plan.cloud}
    authed = {"ollama-cloud": False, "nvidia": False, "codex": False}
    ollama_up = ("ollama-cloud" in kinds or plan.local) and ensure_ollama_running(runner, m.os)
    if "nvidia" in kinds:
        authed["nvidia"] = auth_nvidia(runner, lang, ask, webbrowser.open).status == "ok"
    if "ollama-cloud" in kinds and ollama_up:
        authed["ollama-cloud"] = auth_ollama(runner, lang, ask).status == "ok"
    if "codex" in kinds:
        authed["codex"] = auth_codex(runner, lang, m, ask).status == "ok"

    local = None
    if plan.local and ollama_up:
        tiers = [x for x in cat.local_tiers if x.min_free_mb <= plan.local.min_free_mb]
        local = fit_local(runner, [plan.local] + [x for x in reversed(tiers) if x != plan.local])
        if local is None:
            warnings.append(t("warn.local_failed", lang))
    elif plan.local:
        warnings.append(t("warn.ollama_down", lang))

    now = datetime.now()
    make_backup(home, omh_home, now)
    via_hermes = [c for c in plan.cloud if c.kind in ("nvidia", "codex") and authed[c.kind]]
    if via_hermes:
        try:
            write_aliases(home / "config.yaml", [approved_from(c) for c in via_hermes], home / STATE)
        except ConfigError as e:
            print(t("fatal.config", lang, error=str(e)))
            return EXIT_CONFIG
    results = []
    for c in plan.cloud:
        if not authed[c.kind]:
            continue
        if c.kind == "ollama-cloud":
            r = probe_openai(OLLAMA_BASE + "/v1", "ollama", c.model)
        else:
            r = probe_via_hermes(runner, home, c.alias, c.model)
        print(t("probe.ok", lang, model=c.model, secs=r.latency_s) if r.ok
              else t("probe.fail", lang, model=c.model, reason=r.reason))
        results.append((c, r))

    sel = select(plan, results, local)
    if sel is None:
        print(t("fatal.no_model", lang))
        return EXIT_FATAL
    if sel.main == sel.local:
        warnings.append(t("notes.local_as_main", lang))
    if not configure_and_check(runner, home, omh_home, sel, now, backup=False):
        print(t("fatal.config", lang, error="hermes config check"))
        return EXIT_CONFIG

    approved = [approved_from(c) for c, r in results if r.ok]
    codex = [a for a in approved if a.provider == "openai-codex"]
    omh_args = ["--hermes-home", str(home)] + (["--omh-home", str(args.omh_home)] if args.omh_home else [])
    warnings += apply_omh(runner, plan.executor, hermes_chains(approved, sel.local), maestro_chains(codex),
                          global_args=omh_args)

    report = render_report(lang, m, plan, results, local, sel, warnings)
    (home / REPORT).write_text(report, encoding="utf-8")
    print("\n" + report)
    print(t("done", lang, path=home / REPORT))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
