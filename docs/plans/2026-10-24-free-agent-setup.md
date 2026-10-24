# free-agent-setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um instalador de um comando (Windows + Linux) que configura o Hermes Agent + oh-my-hermes com a melhor combinação gratuita de modelos para a máquina de quem roda.

**Architecture:** O `install.ps1` / `install.sh` só garantem o `uv` e rodam `uv run python -m freeagent`. O pacote Python faz detect → plan → confirm → install → auth → probe → configure → report. Cada módulo tem uma única responsabilidade. Decisões são funções puras (testáveis); efeitos colaterais passam por um `Runner` injetável.

**Tech Stack:** Python ≥ 3.11, uv, ruamel.yaml (round-trip), stdlib (`urllib`, `subprocess`, `getpass`, `argparse`), pytest, ruff, GitHub Actions.

**Spec:** `docs/specs/2026-10-24-free-agent-setup-design.md`

## Global Constraints

- O repositório, as mensagens, os READMEs e os relatórios **não mencionam** o fornecedor pago excluído. Os nomes ficam **só** codificados em base64 em `src/freeagent/policy.py` (`FORBIDDEN_B64 = ("Y2xhdWRl", "YW50aHJvcGlj")`; `forbidden_words() -> tuple[str, ...]` decodifica). Nenhum arquivo contém as palavras literalmente. O executor do OMH desse fornecedor nunca é configurado: `policy.EXCLUDED_EXECUTORS = (forbidden_words()[0] + "-code",)`.
- Nenhum caminho absoluto de usuário, nome, e-mail ou segredo no repositório. O CI barra (Task 12).
- Commits sem trailer de coautoria. O autor é a identidade git local já configurada no repo.
- Só são gravados no config modelos que **passaram no probe** na máquina da pessoa.
- Chaves de API nunca passam pelo código do freeagent. A pessoa as digita no prompt do próprio `hermes auth add`.
- O YAML é editado só com ruamel.yaml round-trip, nunca com substituição de texto.
- Backup antes de qualquer escrita; `hermes config check` depois; rollback automático se a checagem falhar.
- Mensagens ao usuário somente via `t(key, lang)`, com chaves em `en.json` e `pt.json`.
- Faixas de VRAM livre, modelos e contextos exatamente como na spec §3 (`<4096 MB → nenhum`; `4096–6143 → bonsai-2:4b/32k`; `6144–10239 → bonsai-2:9b/64k`; `10240–16383 → bonsai-2:9b/128k`; `≥16384 → bonsai-2:27b/64k`). Contexto mínimo no ajuste: 16384.
- Nome da variante local: `freeagent-local`. Arquivos de estado: `<HERMES_HOME>/freeagent-state.json`, `<HERMES_HOME>/freeagent-backups/<YYYYmmdd-HHMMSS>/` e `<HERMES_HOME>/freeagent-report.md`.

## Review Focus

1. **Várias GPUs** → usar a que tem mais VRAM livre (teste na Task 2).
2. **`nvidia-smi` existe mas falha** (driver quebrado, exit≠0 ou saída vazia) → tratar como sem GPU, sem exceção (teste na Task 2).
3. **Rodar de novo** sobre um config já configurado pelo freeagent → nenhum alias, fallback ou chave duplicada, e só as chaves do freeagent mudam (teste na Task 5).
4. **Config com CRLF e/ou BOM UTF-8** (Windows) → lê, grava, preserva os comentários e não quebra o `hermes config check` (teste na Task 5).
5. **Ollama instalado mas sem servidor rodando** → iniciar e esperar até 30 s pelo `GET /api/version`; se não subir, pular o local com motivo (teste na Task 7).

---

## File Structure

```
install.ps1 / install.sh            bootstrap (Task 11)
pyproject.toml                      pacote + deps + ruff/pytest config (Task 1)
src/freeagent/
  __init__.py, __main__.py          CLI e orquestração (Task 10)
  runner.py                         Runner (subprocess injetável) (Task 1)
  i18n/__init__.py, en.json, pt.json  t() (Task 1)
  redact.py                         mascaramento de segredos (Task 1)
  detect.py                         Machine, parsers (Task 2)
  catalog.json, catalog.py          dados + loader (Task 3)
  plan.py                           make_plan (Task 3)
  backup.py                         backup/restore (Task 4)
  hermes_config.py                  edição do config.yaml (Task 5)
  omh_routing.py                    cadeias do OMH (Task 6)
  probe.py                          testes reais de modelos (Task 7)
  install.py                        instaladores + HERMES_HOME (Task 8)
  auth.py                           logins (Task 9)
  report.py                         relatório (Task 10)
scripts/privacy_scan.py             varredura do CI (Task 12)
.github/workflows/ci.yml            (Task 12)
README.md, docs/README.pt-BR.md, docs/troubleshooting.md  (Task 13)
tests/fixtures/*                    saídas reais de comandos (por task)
```

---

### Task 1: Esqueleto, Runner, i18n e redact

**Files:**
- Create: `pyproject.toml`, `src/freeagent/__init__.py`, `src/freeagent/policy.py` (ver Global Constraints), `src/freeagent/runner.py`, `src/freeagent/i18n/__init__.py`, `src/freeagent/i18n/en.json`, `src/freeagent/i18n/pt.json`, `src/freeagent/redact.py`
- Test: `tests/test_i18n.py`, `tests/test_redact.py`

**Interfaces:**
- Produces:
  - `Runner` protocol: `run(args: list[str], *, timeout: float = 60, input: str | None = None, env: dict | None = None, interactive: bool = False) -> RunResult`.
  - `RunResult(code: int, out: str, err: str)` (dataclass).
  - `SubprocessRunner` (real) e `FakeRunner(responses: dict[tuple[str, ...], RunResult])` em `tests/conftest.py`; o FakeRunner casa pelo prefixo dos args e registra as chamadas em `.calls`.
  - `t(key: str, lang: str, **kw) -> str` (cai para `en` e, sem chave, devolve a própria chave).
  - `redact(text: str) -> str`.

- [ ] **Step 1:** `pyproject.toml` com o pacote `freeagent` (src layout), `requires-python = ">=3.11"`, dependência `ruamel.yaml>=0.18`, dev `pytest`, `ruff`, e o entrypoint `freeagent = "freeagent.__main__:main"`.
- [ ] **Step 2: Testes que falham**

```python
def test_t_pt_and_fallback():
    assert t("plan.title", "pt") == "Plano de instalação"
    assert t("plan.title", "xx") == "Installation plan"
    assert t("missing.key", "pt") == "missing.key"

def test_t_format():
    assert t("probe.ok", "en", model="m", secs=1.5) == "m answered in 1.5s"

def test_en_pt_have_same_keys():
    assert set(load("en")) == set(load("pt"))

# chaves falsas montadas por concatenação ("nvapi" + "-...") para não disparar a varredura
@pytest.mark.parametrize("raw", [FAKE_NVIDIA_KEY, FAKE_SK_KEY, FAKE_BEARER_JWT])
def test_redact_masks(raw):
    out = redact(f"key={raw} done")
    assert raw not in out and "***" in out and out.endswith(" done")

def test_redact_keeps_normal_text():
    assert redact("model gpt-6-luna ok") == "model gpt-6-luna ok"
```

- [ ] **Step 3:** Rodar `uv run pytest tests/test_i18n.py tests/test_redact.py -v` → FAIL (import).
- [ ] **Step 4:** Implementar. O `redact` usa regex para `nvapi-[\w-]{8,}`, `sk-[\w-]{16,}`, `Bearer\s+\S+` e JWT `eyJ[\w-]+\.[\w-]+\.[\w-]+`, trocando por `***`. O i18n carrega o JSON via `importlib.resources`.
- [ ] **Step 5:** Rodar os testes → PASS; `uv run ruff check` → limpo.
- [ ] **Step 6:** Commit `feat: scaffold package, runner, i18n and redaction`.

---

### Task 2: Detecção da máquina

**Files:**
- Create: `src/freeagent/detect.py`, `tests/fixtures/nvidia_smi_one.csv`, `tests/fixtures/nvidia_smi_two.csv`, `tests/fixtures/rocm_smi.json`
- Test: `tests/test_detect.py`

**Interfaces:**
- Consumes: `Runner`.
- Produces (dataclasses frozen):
  - `Gpu(vendor: str, name: str, vram_total_mb: int, vram_free_mb: int)`
  - `Tools(hermes: bool, omh: bool, ollama: bool, codex: bool, codex_logged_in: bool, other_agents: tuple[str, ...])`
  - `Machine(os: str, gpu: Gpu | None, ram_gb: float, cpu_cores: int, disk_free_gb: float, lang: str, tools: Tools)`; `os ∈ {"windows","linux"}`, `lang ∈ {"pt","en"}`.
  - `parse_nvidia_smi(text: str) -> list[Gpu]` (entrada: `nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits`).
  - `parse_rocm_smi(text: str) -> list[Gpu]` (entrada: `rocm-smi --showmeminfo vram --showproductname --json`).
  - `best_gpu(gpus: list[Gpu]) -> Gpu | None`
  - `detect_lang(lang_env: str | None, culture: str | None) -> str`
  - `detect_machine(runner: Runner, which: Callable[[str], str | None] = shutil.which) -> Machine`

- [ ] **Step 1: Testes que falham**

```python
def test_parse_nvidia_one():
    [g] = parse_nvidia_smi("NVIDIA GeForce RTX 3060 Ti, 8192, 6937\n")
    assert g == Gpu("nvidia", "NVIDIA GeForce RTX 3060 Ti", 8192, 6937)

def test_best_gpu_picks_most_free():          # Review Focus 1
    gpus = parse_nvidia_smi(fixture("nvidia_smi_two.csv"))
    assert best_gpu(gpus).vram_free_mb == max(g.vram_free_mb for g in gpus)

def test_nvidia_smi_failure_means_no_gpu(fake_runner):   # Review Focus 2
    fake_runner.set(("nvidia-smi",), RunResult(9, "", "NVML error"))
    m = detect_machine(fake_runner, which=lambda c: "/x/" + c if c == "nvidia-smi" else None)
    assert m.gpu is None

def test_parse_rocm():
    [g] = parse_rocm_smi(fixture("rocm_smi.json"))
    assert g.vendor == "amd" and g.vram_total_mb > 0

@pytest.mark.parametrize("env,cult,exp", [("pt_BR.UTF-8", None, "pt"), (None, "pt-BR", "pt"), ("en_US.UTF-8", None, "en"), (None, None, "en")])
def test_detect_lang(env, cult, exp):
    assert detect_lang(env, cult) == exp

def test_codex_logged_in_from_status(fake_runner):
    fake_runner.set(("codex", "login", "status"), RunResult(0, "Logged in using ChatGPT", ""))
    m = detect_machine(fake_runner, which=lambda c: "/x/codex" if c == "codex" else None)
    assert m.tools.codex and m.tools.codex_logged_in
```

- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar. RAM e disco via `psutil`? **Não**: use stdlib. No Windows, `ctypes` `GlobalMemoryStatusEx`; no Linux, `/proc/meminfo`. Disco: `shutil.disk_usage(home)`. Núcleos: `os.cpu_count()`. Idioma no Windows: `Get-Culture` via `powershell -NoProfile -Command (Get-Culture).Name`. `other_agents`: binários presentes entre `("gemini", "agy", "cursor-agent", "opencode")`; só são listados no relatório, nunca configurados. Qualquer exceção de um sub-detector vira o valor padrão (sem GPU, sem a ferramenta).
- [ ] **Step 4:** Rodar → PASS.
- [ ] **Step 5:** Commit `feat: detect hardware, language and installed tools`.

---

### Task 3: Catálogo e plano

**Files:**
- Create: `src/freeagent/catalog.json`, `src/freeagent/catalog.py`, `src/freeagent/plan.py`
- Test: `tests/test_plan.py`

**Interfaces:**
- Consumes: `Machine`.
- Produces:
  - `LocalTier(min_free_mb: int, max_free_mb: int | None, model: str, download_gb: float, ctx: int)`
  - `CloudCandidate(id: str, kind: str, model: str, alias: str, tier: str)`; `kind ∈ {"nvidia","ollama-cloud","codex"}`, `tier ∈ {"heavy","mid","fast"}`.
  - `Catalog(local_tiers: list[LocalTier], cloud: list[CloudCandidate])`; `load_catalog() -> Catalog`.
  - `Plan(local: LocalTier | None, cloud: list[CloudCandidate], install: list[str], executor: str, notes: list[str])`; `install ⊆ ["ollama","hermes","omh"]` em ordem; `executor ∈ {"codex","hermes"}`.
  - `make_plan(m: Machine, cat: Catalog, *, skip_local: bool = False, skip_cloud: bool = False) -> Plan`

- [ ] **Step 1:** `catalog.json` com as 4 faixas da Global Constraints e os candidatos de nuvem **nesta ordem** (a ordem é a prioridade do modelo principal):
  - `nvidia-nemotron-ultra`: nvidia, `nvidia/nemotron-3-ultra-550b-a55b`, alias `nemotron`, heavy
  - `ollama-nemotron-ultra`: ollama-cloud, `nemotron-3-ultra:cloud`, alias `nemotron-ollama`, heavy
  - `ollama-nemotron-super`: ollama-cloud, `nemotron-3-super:cloud`, alias `nemotron-super`, mid
  - `ollama-gemma4`: ollama-cloud, `gemma4:31b-cloud`, alias `gemma-cloud`, mid
  - `codex-gpt-6.1-sol` (heavy), `codex-gpt-6-astra` (heavy), `codex-gpt-6-luna` (fast), `codex-gpt-5.6-terra` (mid), `codex-gpt-reserve` (fast): kind codex, alias `codex-<model>`
- [ ] **Step 2: Testes que falham**

```python
@pytest.mark.parametrize("free,model,ctx", [(3000, None, None), (5000, "bonsai-2:4b", 32768), (6937, "bonsai-2:9b", 65536), (12000, "bonsai-2:9b", 131072), (20000, "bonsai-2:27b", 65536)])
def test_local_tier_by_free_vram(free, model, ctx):
    p = make_plan(machine(gpu_free=free), load_catalog())
    assert (p.local.model if p.local else None) == model
    assert (p.local.ctx if p.local else None) == ctx

def test_no_gpu_no_local():
    assert make_plan(machine(gpu=None), load_catalog()).local is None

def test_codex_candidates_only_when_logged_in():
    kinds = {c.kind for c in make_plan(machine(codex_logged_in=False), load_catalog()).cloud}
    assert "codex" not in kinds

def test_executor():
    assert make_plan(machine(codex_logged_in=True), load_catalog()).executor == "codex"
    assert make_plan(machine(codex_logged_in=False), load_catalog()).executor == "hermes"

def test_install_list_missing_only_and_ordered():
    p = make_plan(machine(hermes=False, omh=False, ollama=True), load_catalog())
    assert p.install == ["hermes", "omh"]

def test_ollama_installed_only_if_needed():
    p = make_plan(machine(gpu=None, ollama=False), load_catalog(), skip_cloud=True)
    assert "ollama" not in p.install

def test_skip_flags():
    p = make_plan(machine(gpu_free=7000), load_catalog(), skip_local=True, skip_cloud=True)
    assert p.local is None and p.cloud == []

def test_catalog_has_no_forbidden_vendor():
    text = (resources.files("freeagent") / "catalog.json").read_text().lower()
    assert not any(w in text for w in forbidden_words())
```

`machine(...)` é um builder de teste em `tests/conftest.py` com defaults (linux, GPU nvidia 8192/7000, todas as ferramentas ausentes, lang en).
- [ ] **Step 3:** Rodar → FAIL. **Step 4:** Implementar. O Ollama entra em `install` se `local` não for None **ou** se existir candidato ollama-cloud. **Step 5:** PASS. **Step 6:** Commit `feat: catalog and pure install plan`.

---

### Task 4: Backup e restauração

**Files:**
- Create: `src/freeagent/backup.py`
- Test: `tests/test_backup.py`

**Interfaces:**
- Produces: `make_backup(hermes_home: Path, omh_home: Path, now: datetime) -> Path` (copia `config.yaml`, `.env`, `auth.json` se existirem, e `omh_home/routing/`); `restore_latest(hermes_home: Path, omh_home: Path) -> Path | None`.

- [ ] **Step 1: Testes**: `test_backup_then_restore_roundtrip` (modifica os arquivos depois do backup; o restore devolve o conteúdo exato, byte a byte); `test_restore_without_backup_returns_none`; `test_backup_skips_missing_files`; `test_latest_is_newest_timestamp` (dois backups; restaura o mais novo).
- [ ] **Step 2:** FAIL. **Step 3:** Implementar com `shutil.copy2` / `copytree(dirs_exist_ok=True)`. **Step 4:** PASS. **Step 5:** Commit `feat: backup and rollback of hermes/omh config`.

---

### Task 5: Edição do config do Hermes

**Files:**
- Create: `src/freeagent/hermes_config.py`, `tests/fixtures/config_sample.yaml` (com `# model_aliases:` comentado antes do bloco real, comentários e um bloco `auxiliary` no fim do arquivo)
- Test: `tests/test_hermes_config.py`

**Interfaces:**
- Produces:
  - `Approved(alias: str, provider: str, model: str, base_url: str | None = None, api_key: str | None = None, tier: str = "mid")`; para o Ollama, `provider="custom"`, `base_url="http://127.0.0.1:11434/v1"`, `api_key="ollama"`.
  - `Selection(main: Approved, fallbacks: list[Approved], local: Approved | None, compression: Approved, aliases: list[Approved])`
  - `find_duplicate_keys(text: str) -> list[str]` (caminhos `a.b` duplicados no mesmo mapping)
  - `apply_selection(path: Path, sel: Selection, state_path: Path) -> None` (lê, aplica e grava, preservando EOL e BOM)
  - `write_aliases(path: Path, aliases: list[Approved], state_path: Path) -> None`: só a parte de `model_aliases` de `apply_selection`, com as mesmas regras de state. Serve para gravar os aliases provisórios antes dos probes via Hermes; `apply_selection` a reutiliza.

O que `apply_selection` grava:
  - `model.provider` / `model.default` / `model.base_url` (`''` se None) ← `main`;
  - `fallback_providers` ← `fallbacks`, substituindo **só** as entradas registradas no state anterior;
  - `model_aliases.<alias>` ← cada um de `aliases`, removendo antes os aliases do state anterior;
  - `auxiliary.compression` ← `compression` com `reasoning_effort: low`;
  - `auxiliary.{title_generation,session_search,web_extract}` ← `local` com `timeout: 120` e `fallback_chain: [compression]`; se `local` for None, recebe `compression`.
  - o state guarda os aliases e os fallbacks gravados.

- [ ] **Step 1: Testes que falham**

```python
def test_preserves_comments_and_real_alias_block(tmp_path):
    cfg = copy_fixture(tmp_path); apply_selection(cfg, sel(), tmp_path / "s.json")
    text = cfg.read_text(encoding="utf-8-sig")
    assert "# model_aliases:" in text                       # comentário intacto
    assert yaml_load(cfg)["model_aliases"]["nemotron"]["provider"] == "nvidia"

def test_rerun_is_idempotent(tmp_path):                       # Review Focus 3
    cfg = copy_fixture(tmp_path); st = tmp_path / "s.json"
    apply_selection(cfg, sel(), st); first = cfg.read_bytes()
    apply_selection(cfg, sel(), st)
    assert cfg.read_bytes() == first and find_duplicate_keys(cfg.read_text("utf-8-sig")) == []

def test_rerun_replaces_only_own_aliases(tmp_path):
    cfg = copy_fixture(tmp_path, extra_alias="mine")          # alias do usuário
    st = tmp_path / "s.json"
    apply_selection(cfg, sel(aliases=["a", "b"]), st); apply_selection(cfg, sel(aliases=["a"]), st)
    assert set(yaml_load(cfg)["model_aliases"]) == {"mine", "a"}

def test_crlf_and_bom_preserved(tmp_path):                    # Review Focus 4
    cfg = copy_fixture(tmp_path, crlf=True, bom=True); apply_selection(cfg, sel(), tmp_path / "s.json")
    raw = cfg.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")

def test_detects_preexisting_duplicate():
    assert find_duplicate_keys("plugins:\n  enabled: []\n  enabled: [x]\n") == ["plugins.enabled"]

def test_aux_without_local_uses_compression(tmp_path):
    cfg = copy_fixture(tmp_path); apply_selection(cfg, sel(local=None), tmp_path / "s.json")
    assert yaml_load(cfg)["auxiliary"]["title_generation"]["model"] == sel().compression.model
```

- [ ] **Step 2:** FAIL. **Step 3:** Implementar com `ruamel.yaml.YAML()` (round-trip, `preserve_quotes=True`, `width=4096`). EOL e BOM são detectados nos bytes, normalizados para LF no parse e restaurados ao gravar. Se `find_duplicate_keys` achar duplicatas **antes** de editar, `apply_selection` levanta `ConfigError` com a lista (quem chama decide; ruamel recusa duplicatas). **Step 4:** PASS. **Step 5:** Commit `feat: structured, idempotent hermes config editing`.

---

### Task 6: Cadeias do OMH

**Files:**
- Create: `src/freeagent/omh_routing.py`
- Test: `tests/test_omh_routing.py`

**Interfaces:**
- Consumes: `Approved`, `Runner`.
- Produces:
  - `CATEGORIES = {"heavy": ("ultrabrain","architect","deep","deep-work"), "mid": ("unspecified-high","capable","writing","visual-engineering","artistry"), "fast": ("unspecified-low","quick","simple-work")}`
  - `EFFORT = {"ultrabrain":"xhigh","architect":"xhigh","deep":"high","deep-work":"high", **{c:"medium" for c in mid}, **{c:"low" for c in fast}}`
  - `hermes_chains(approved: list[Approved], local: Approved | None) -> dict[str, list[str]]`: cada categoria recebe `model:effort`. Heavy usa os aprovados em ordem de prioridade com o tier heavy primeiro; mid usa mid primeiro, depois heavy; fast usa fast primeiro e o local por último. Sem duplicatas.
  - `maestro_chains(codex_models: list[Approved]) -> dict[str, list[str]]`: o mesmo, só com os modelos do Codex.
  - `apply_omh(runner: Runner, executor: str, chains: dict, maestro: dict) -> list[str]`: roda `omh setup --scope user --yes --no-interactive --default-executor <executor>`, depois `omh model-chains set <cat> "<a, b>"` e `omh coding category-maestro set codex <cat> <a> <b>`. Devolve os avisos.

- [ ] **Step 1: Testes**: `test_every_category_present`; `test_heavy_prefers_heavy_tier` (com um heavy e um fast, o heavy vem primeiro em `ultrabrain` com `:xhigh`); `test_fast_prefers_fast_then_local`; `test_no_duplicates_per_chain`; `test_apply_commands` (o FakeRunner recebe exatamente `["omh","setup","--scope","user","--yes","--no-interactive","--default-executor","codex"]` primeiro e 12 chamadas `model-chains set`); `test_maestro_skipped_without_codex` (`maestro_chains([]) == {}` e nenhuma chamada `category-maestro`).
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS.
- [ ] **Step 5: Verificação do modelo local no OMH.** Na máquina real, com um `HERMES_HOME` isolado, rodar `omh model-chains set quick "freeagent-local:low"` e depois `omh model-chains show`. Se o OMH aceitar, mantenha o local nas cadeias. Se não aceitar, `hermes_chains` deixa o local de fora e `report` registra o aviso `report.local_not_in_omh`. Registrar o resultado no docstring de `hermes_chains`.
- [ ] **Step 6:** Commit `feat: omh routing from probed models only`.

---

### Task 7: Probes

**Files:**
- Create: `src/freeagent/probe.py`, `tests/fixtures/ollama_ps_full_gpu.txt`, `tests/fixtures/ollama_ps_split.txt`, `tests/fixtures/agent_log_tail.txt`
- Test: `tests/test_probe.py`

**Interfaces:**
- Consumes: `Runner`, `LocalTier`, `CloudCandidate`, `Approved`.
- Produces:
  - `ProbeResult(id: str, ok: bool, latency_s: float | None, reason: str)`
  - `parse_ollama_ps(text: str) -> dict[str, int]` (modelo → % GPU; `"9%/91% CPU/GPU"` → 91, `"100% GPU"` → 100)
  - `probe_openai(base_url: str, api_key: str, model: str, timeout: float = 90) -> ProbeResult` (POST `/chat/completions`, `"Reply only: OK"`, `max_tokens=300`; ok = HTTP 200 com conteúdo não vazio; reason = `http_402`/`http_404`/`timeout`/…)
  - `last_served(log_text: str, session_hint: str | None = None) -> tuple[str, str] | None` (provider, model da última linha `API call #1:`)
  - `probe_via_hermes(runner: Runner, hermes_home: Path, alias: str, expect_model: str) -> ProbeResult` (roda `hermes chat --oneshot -m <alias> -q "Reply only: OK"` com `HERMES_HOME`; ok **só se** `last_served` do `logs/agent.log` devolver `expect_model`, pois um fallback que responde não conta)
  - `ensure_ollama_running(runner: Runner, os: str, wait_s: int = 30) -> bool`
  - `LocalResult(model: str, ctx: int, gpu_pct: int, tok_s: float)`
  - `fit_local(runner: Runner, tier_chain: list[LocalTier]) -> LocalResult | None`

O algoritmo do `fit_local`, para cada faixa a partir da escolhida e descendo:
  1. `ollama pull <model>`;
  2. cria `freeagent-local` com um Modelfile `FROM <model>` / `PARAMETER num_ctx <ctx>`;
  3. `POST /api/generate` (`stream:false`, `think:false`, `num_predict:200`), com tok/s = `eval_count/(eval_duration/1e9)`;
  4. `parse_ollama_ps`: se der 100, retorna; senão `ctx //= 2`. Com `ctx < 16384`, passa para a faixa seguinte; sem faixas, `None`.

- [ ] **Step 1: Testes que falham**

```python
def test_parse_ollama_ps():
    assert parse_ollama_ps(fixture("ollama_ps_full_gpu.txt"))["bonsai-2:9b"] == 100
    assert parse_ollama_ps(fixture("ollama_ps_split.txt"))["qwen2.5-coder:7b"] == 91

def test_last_served():
    assert last_served(fixture("agent_log_tail.txt")) == ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b")

def test_probe_via_hermes_rejects_fallback(fake_runner, tmp_home):
    write_log(tmp_home, provider="openai-codex", model="gpt-5.6-terra")   # quem respondeu foi o fallback
    r = probe_via_hermes(fake_runner, tmp_home, "nemotron", "nvidia/nemotron-3-ultra-550b-a55b")
    assert not r.ok and r.reason == "served_by_other"

def test_probe_openai_maps_402(http_server_402):
    assert probe_openai(http_server_402.url, "x", "m").reason == "http_402"

def test_fit_local_halves_ctx_then_succeeds(fake_ollama):     # 64k = 91% → 32k = 100%
    r = fit_local(fake_ollama.runner, [tier(ctx=65536)])
    assert r.ctx == 32768 and r.gpu_pct == 100

def test_fit_local_gives_up(fake_ollama_never_full):
    assert fit_local(fake_ollama_never_full.runner, [tier(ctx=32768)]) is None

def test_ollama_not_running_times_out(fake_runner_no_server):  # Review Focus 5
    assert ensure_ollama_running(fake_runner_no_server, "linux", wait_s=1) is False
```

As fixtures `http_server_*` usam `http.server` numa thread com porta 0. `fake_ollama` é um FakeRunner mais um servidor HTTP fake de `/api/generate`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. Para iniciar o Ollama: no Windows, `ollama app.exe` (descoberto via `where ollama`, mesma pasta); no Linux, `systemctl --user start ollama` ou `ollama serve` em background. **Step 4:** PASS. **Step 5:** Commit `feat: real model probes and local GPU fitting`.

---

### Task 8: Instaladores e HERMES_HOME

**Files:**
- Create: `src/freeagent/install.py`
- Test: `tests/test_install.py`

**Interfaces:**
- Consumes: `Runner`, `Machine`.
- Produces:
  - `INSTALLERS: dict[tuple[str, str], list[str]]`, com (componente, os) → comando:
    - `("ollama","windows")`: `winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements --silent`
    - `("ollama","linux")`: `sh -c "curl -fsSL https://ollama.com/install.sh | sh"`
    - `("hermes","windows")`: `powershell -NoProfile -Command "& ([scriptblock]::Create((irm https://hermes-agent.nousresearch.com/install.ps1))) -SkipSetup"`
    - `("hermes","linux")`: o script oficial `https://hermes-agent.nousresearch.com/install.sh` com o flag de pular o setup verificado no Step 1
    - `("omh","windows")`: `powershell -NoProfile -Command "irm https://raw.githubusercontent.com/rlaope/oh-my-hermes/main/install.ps1 | iex"`
    - `("omh","linux")`: o equivalente `install.sh` do mesmo repositório (verificado no Step 1)
  - `installer_url(component: str, os: str) -> str` (mostrado ao usuário antes de rodar)
  - `ensure_installed(runner: Runner, m: Machine, components: list[str]) -> dict[str, str]` (componente → `ok`/`failed:<motivo>`; depois de instalar, refaz o PATH a partir do registro no Windows)
  - `resolve_hermes_home(runner: Runner, os: str, env: Mapping[str, str]) -> Path`: um `HERMES_HOME` válido no env ganha; senão, pergunta ao Hermes (comando verificado no Step 1); senão, `%LOCALAPPDATA%\hermes` no Windows e `~/.hermes` no Linux. Válido = o diretório contém `config.yaml`.
  - `persist_hermes_home(runner: Runner, os: str, home: Path) -> None`: Windows via `[Environment]::SetEnvironmentVariable('HERMES_HOME', …, 'User')`; Linux com uma linha `export HERMES_HOME=…` marcada `# freeagent` em `~/.profile`, sem duplicar.

- [ ] **Step 1: Investigação (sem código).** Baixar e ler `https://hermes-agent.nousresearch.com/install.sh`, o `install.ps1` e o `install.sh` do oh-my-hermes, e rodar `hermes config --help`. Anotar: (a) o flag do Linux equivalente a `-SkipSetup`; (b) se existe `install.sh` do OMH; (c) um comando que imprima o home do Hermes. Gravar as respostas como constantes comentadas em `install.py`. Se (c) não existir, usar só os defaults por SO.
- [ ] **Step 2: Testes**: `test_installer_urls_are_https_official` (todo `installer_url` começa com um dos 4 domínios: `ollama.com`, `hermes-agent.nousresearch.com`, `raw.githubusercontent.com/rlaope/oh-my-hermes`, ou é winget); `test_resolve_prefers_valid_env`; `test_resolve_ignores_env_without_config` (env aponta para um dir vazio → cai no default por SO); `test_resolve_windows_default`; `test_persist_linux_idempotent` (duas chamadas → uma linha `# freeagent` no `.profile`); `test_ensure_installed_reports_failure` (exit≠0 → `failed:exit_1`, sem exceção).
- [ ] **Step 3:** FAIL. **Step 4:** Implementar. **Step 5:** PASS. **Step 6:** Commit `feat: official installers and HERMES_HOME resolution`.

---

### Task 9: Autenticação

**Files:**
- Create: `src/freeagent/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `Runner`, `t`.
- Produces:
  - `AuthOutcome(provider: str, status: str)` com `status ∈ {"ok","skipped","failed"}`
  - `auth_nvidia(runner, lang, ask: Callable[[str], bool], open_url: Callable[[str], None]) -> AuthOutcome`: se `hermes auth status nvidia` já disser "logged in", devolve `ok` sem perguntar. Senão pergunta se quer ativar; se sim, abre `https://build.nvidia.com/` e roda `hermes auth add nvidia --type api-key` com `interactive=True`, para a pessoa digitar a chave no prompt oculto do próprio Hermes.
  - `auth_ollama(runner, lang, ask) -> AuthOutcome`: roda `ollama signin` (interactive) se `ask` aceitar. Para checar o login, um `probe_openai` em `nemotron-3-ultra:cloud` no Ollama local que **não** devolva 401.
  - `auth_codex(runner, lang, ask) -> AuthOutcome`: só se `codex_logged_in`; já logado (`hermes auth status openai-codex`) vira `ok`; senão roda `hermes auth add openai-codex --type oauth` (interactive).
  - Com `--yes`, `ask` responde True a tudo, mas os logins interativos continuam acontecendo; se a pessoa cancelar, vira `skipped`.

- [ ] **Step 1: Testes**: `test_nvidia_already_logged_in_no_prompt` (nenhuma chamada a `ask` nem a `auth add`); `test_nvidia_declined_is_skipped`; `test_nvidia_runs_hermes_prompt_interactively` (a chamada registrada tem `interactive=True` e **nenhum** argumento `--api-key`); `test_codex_not_offered_when_cli_absent`; `test_failed_login_is_failed_not_exception`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS. **Step 5:** Commit `feat: optional provider logins via official commands`.

---

### Task 10: Seleção, relatório e orquestração da CLI

**Files:**
- Create: `src/freeagent/report.py`, `src/freeagent/__main__.py`, `src/freeagent/select.py`
- Test: `tests/test_select.py`, `tests/test_report.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: tudo o que veio antes.
- Produces:
  - `select(plan: Plan, results: list[tuple[CloudCandidate, ProbeResult]], local: LocalResult | None) -> Selection | None`: main = primeiro aprovado em ordem de catálogo; se não houver nuvem, main = local, com a nota `notes.local_as_main`; `None` se não houver nada. fallbacks = demais aprovados; compression = primeiro aprovado de nuvem, ou local; aliases = todos os aprovados mais `local` (alias `local`).
  - `render_report(lang: str, machine: Machine, plan: Plan, results, local, selection, warnings: list[str]) -> str` (Markdown, sempre passado por `redact`)
  - `main(argv: list[str] | None = None, runner: Runner | None = None) -> int`, com os flags da spec §8: `--dry-run`, `--yes`, `--lang`, `--skip-local`, `--skip-cloud`, `--rollback`.

Fluxo do `main`:
  1. detect e plan; imprime o plano com o motivo de cada item;
  2. `--dry-run` retorna 0 aqui;
  3. confirm;
  4. `ensure_installed`; `resolve_hermes_home` + `persist_hermes_home`;
  5. auth;
  6. `ensure_ollama_running` + `fit_local`;
  7. probes: Ollama Cloud via `probe_openai` local; NVIDIA e Codex: faz o backup, grava **antes** os aliases provisórios (`write_aliases` com todos os candidatos) e roda `probe_via_hermes`;
  8. `select`;
  9. backup → `apply_selection` → `hermes config check`; se falhar, `restore_latest` e retorna 2;
  10. `apply_omh`;
  11. report, gravado em `freeagent-report.md`, com o resumo no terminal.

Os códigos de saída são `0` ok, `1` cancelado, `2` falha de config, `3` falha fatal (Hermes não instalou, sem internet). `--rollback` chama `restore_latest` e retorna 0 se restaurou, 1 se não havia backup.

- [ ] **Step 1: Testes**: `test_select_order_and_fallbacks`; `test_select_local_as_main_when_no_cloud`; `test_select_none`; `test_report_redacts_and_has_no_forbidden_words` (injeta uma chave NVIDIA falsa (montada por concatenação) num warning; o relatório não contém o segredo nem nenhuma de `forbidden_words()`); `test_report_pt_and_en_headings`; `test_main_dry_run_writes_nothing` (FakeRunner; nenhuma chamada além de detect; nenhum arquivo criado em tmp HERMES_HOME); `test_main_restores_on_failed_check` (o FakeRunner faz `hermes config check` sair com 1 → arquivos iguais aos originais, exit 2); `test_main_rollback_without_backup_returns_1`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS.
- [ ] **Step 5:** Rodar `uv run python -m freeagent --dry-run --lang pt` nesta máquina e conferir que o plano mostra a GPU, a faixa `bonsai-2:9b/64k`, os candidatos e o executor `codex`.
- [ ] **Step 6:** Commit `feat: selection, report and CLI orchestration`.

---

### Task 11: Bootstrap de uma linha

**Files:**
- Create: `install.ps1`, `install.sh`
- Test: `tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `freeagent.__main__:main` via `uv run`.
- Produces: `irm https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.ps1 | iex` e `curl -fsSL https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.sh | bash`. Os argumentos são repassados: `$env:FREEAGENT_ARGS` no `irm | iex`; `bash -s -- <args>` no curl.

Comportamento:
  1. se o `uv` não estiver no PATH, instala com o instalador oficial (`https://astral.sh/uv/install.ps1` / `install.sh`) e atualiza o PATH da sessão;
  2. se estiver rodando dentro de um clone (existe `pyproject.toml` com `name = "freeagent"` ao lado do script), usa o clone; senão baixa o tarball de `main` (`https://github.com/Jaimedsf/free-agent-setup/archive/refs/heads/main.tar.gz` / `.zip`) para uma pasta temporária nova;
  3. `uv run --project <dir> python -m freeagent <args>`;
  4. propaga o exit code. Nada de `Set-ExecutionPolicy`.

- [ ] **Step 1: Testes**: `test_bootstrap_scripts_small` (cada script tem ≤ 60 linhas não vazias); `test_bootstrap_urls_official` (todas as URLs são `astral.sh`, `github.com/Jaimedsf/free-agent-setup` ou `raw.githubusercontent.com/Jaimedsf/free-agent-setup`); `test_install_sh_shellcheck_clean` (se o `shellcheck` estiver disponível; senão skip).
- [ ] **Step 2:** FAIL. **Step 3:** Escrever os scripts. **Step 4:** PASS. Rodar o `install.ps1` local com `$env:FREEAGENT_ARGS="--dry-run"` → mostra o plano e sai com 0. Rodar `bash install.sh --dry-run` no WSL → idem.
- [ ] **Step 5:** Commit `feat: one-line bootstrap for windows and linux`.

---

### Task 12: CI e varredura de privacidade

**Files:**
- Create: `scripts/privacy_scan.py`, `.github/workflows/ci.yml`
- Test: `tests/test_privacy_scan.py`

**Interfaces:**
- Produces: `scan(paths: list[Path]) -> list[str]` (achados `arquivo:linha: motivo`); `python scripts/privacy_scan.py` sai com 1 se houver achados.

Padrões proibidos: `[A-Za-z]:\\Users\\[^\\%$<]+` (exceto o literal `%LOCALAPPDATA%`), `/home/[a-z][\w-]*/` (exceto `/home/runner/` em logs de CI), e-mails que não sejam `@users.noreply.github.com`, `nvapi-[\w-]{8,}`, `sk-[\w-]{16,}`, `gh[pousr]_\w{20,}`, e as palavras de `freeagent.policy.forbidden_words()` (case-insensitive). O script ignora a si mesmo e a `tests/test_privacy_scan.py` só nos padrões de caminho, e-mail e segredo (que precisam aparecer como exemplo); as palavras proibidas nunca são isentas, porque nenhum arquivo precisa delas.

- [ ] **Step 1: Testes**: um caso positivo por padrão e um negativo (`%LOCALAPPDATA%\hermes`, o e-mail noreply e `~/.hermes` passam).
- [ ] **Step 2:** FAIL. **Step 3:** Implementar o scan. O `ci.yml` roda uma matriz `windows-latest` e `ubuntu-latest` com `astral-sh/setup-uv`, `uv run ruff check`, `uv run pytest`, `uv run python -m freeagent --dry-run --yes --lang en` (precisa sair com 0 numa máquina sem GPU nem ferramentas) e `uv run python scripts/privacy_scan.py`.
- [ ] **Step 4:** PASS local e scan limpo no repositório inteiro.
- [ ] **Step 5:** Commit `ci: tests, dry-run and privacy scan on windows and linux`.

---

### Task 13: Documentação

**Files:**
- Create: `README.md` (en), `docs/README.pt-BR.md`, `docs/troubleshooting.md`, `LICENSE` (MIT)

Conteúdo, nos dois idiomas e com as mesmas seções:
  - o que é e para quem;
  - o comando de uma linha (Windows e Linux);
  - o que o instalador faz, nas 8 etapas;
  - a tabela de VRAM → modelo local;
  - a ordem dos provedores grátis e o que cada um exige (chave NVIDIA, login Ollama, Codex já logado);
  - os flags;
  - como trocar de modelo (`/model <alias>`);
  - rollback;
  - privacidade (o que fica só na máquina, sem telemetria);
  - limitações (contexto do modelo local, limites dos planos gratuitos, uma requisição por vez no Ollama Free).

O `troubleshooting.md` cobre: OMH configurado no `HERMES_HOME` errado; `config check` falhando; modelo que transborda para a CPU; 402 do plano gratuito; alias que cai no fallback; Ollama sem servidor.

- [ ] **Step 1:** Escrever. **Step 2:** `uv run python scripts/privacy_scan.py` → limpo. Os comandos dos READMEs são idênticos às URLs da Task 11.
- [ ] **Step 3:** Commit `docs: bilingual readme and troubleshooting`.

---

### Task 14: Validação real e publicação

- [ ] **Step 1:** Nesta máquina, com `HERMES_HOME` e `OMH_HOME` temporários e isolados (sem tocar no Hermes atual do usuário), rodar o instalador completo com `--yes`. Conferir: (a) o relatório lista os probes aprovados e rejeitados; (b) `hermes config check` limpo; (c) `/plugins` mostra o omh; (d) o `ollama ps` mostra `freeagent-local` em 100% GPU; (e) uma segunda execução não altera o config (`git diff --no-index` vazio entre as duas cópias); (f) `--rollback` restaura.
- [ ] **Step 2:** No WSL Ubuntu: `bash install.sh --dry-run` e uma execução completa sem GPU (`--skip-local`). Conferir a saída 0 e o relatório.
- [ ] **Step 3:** Rodar o `privacy_scan` no repositório inteiro e revisar o `git log -p` atrás de dados pessoais.
- [ ] **Step 4:** Com a confirmação do usuário: `gh repo create Jaimedsf/free-agent-setup --public --source . --push` e conferir que o CI ficou verde.
- [ ] **Step 5:** Testar a linha única real a partir do GitHub (`irm …/install.ps1 | iex` com `FREEAGENT_ARGS=--dry-run`).
