# free-agent-setup

[Português](docs/README.pt-BR.md) · [Troubleshooting](docs/troubleshooting.md)

One command sets up a **free, hardware-aware AI coding agent** on your machine:
[Hermes Agent](https://hermes-agent.nousresearch.com/) with [oh-my-hermes](https://github.com/rlaope/oh-my-hermes) workflows.
The installer looks at your computer, picks the best mix of **free** models, and checks that every model it configures
really answers on your account before writing it to the config.

## Install

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.ps1 | iex
```

**Linux**:

```bash
curl -fsSL https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.sh | bash
```

You see the plan first and confirm once. Nothing is installed before that.

## What it does

1. **Detect**: OS, GPU and free VRAM (NVIDIA or AMD), RAM, CPU, disk, language, and the tools you already have
   (Hermes, oh-my-hermes, Ollama, Codex CLI, other agent CLIs).
2. **Plan**: chooses a local model that fits your GPU, the free cloud providers to try and the coding executor.
3. **Confirm**: shows the plan with the reason for each item.
4. **Install** what is missing, using each project's official installer (the Hermes wizard is skipped; this tool
   configures it).
5. **Sign in** to free providers. Each one is optional, and keys are typed into Hermes' own hidden prompt.
6. **Probe**: sends a tiny "Reply only: OK" to every candidate. Models that return an error, need a paid plan or time
   out are left out. The local model is checked to run **100% on the GPU**.
7. **Configure** Hermes and oh-my-hermes with only the models that passed. Your config is backed up first and validated
   with `hermes config check`; if validation fails, the backup is restored automatically.
8. **Report**: prints a summary and saves `freeagent-report.md` in your Hermes folder.

## Local model (runs on your GPU)

| Free VRAM | Model | Download | Target context |
|---|---|---|---|
| under 4 GB, or no GPU | none (CPU-only would be slow) | — | — |
| 4–6 GB | `bonsai-2:4b` | 1.6 GB | 32k |
| 6–10 GB | `bonsai-2:9b` | 3.2 GB | 64k |
| 10–16 GB | `bonsai-2:9b` | 3.2 GB | 128k |
| 16 GB and up | `bonsai-2:27b` | 8.3 GB | 64k |

If the model does not fit fully on the GPU, the context is halved (down to 16k), and then a smaller model is tried.
The local model handles light tasks (session titles, search, web page extraction). It is not the main model, because
long coding sessions need far more context than a small local model holds.

## Free providers (main model, tried in this order)

| Provider | What you need | Model |
|---|---|---|
| NVIDIA build | a free API key from [build.nvidia.com](https://build.nvidia.com/) | `nemotron-3-ultra` |
| Ollama Cloud | a free account (`ollama signin`) | `nemotron-3-ultra:cloud`, `nemotron-3-super:cloud`, `gemma4:31b-cloud` |
| Google AI Studio | a free API key from [aistudio.google.com](https://aistudio.google.com/apikey) | `gemini-3.6-flash`, `gemini-3.5-flash-lite` |
| Codex | only if the Codex CLI is already signed in on this machine | the models your plan accepts |

The first model that passes becomes the main model, and the others become automatic fallbacks. If none passes, the
local model becomes the main model and the report says so. Providers billed per token are never configured.

## Options

```
--dry-run      detect and show the plan, change nothing
--yes          skip the confirmation (browser sign-ins still ask)
--lang pt|en   force the language (default: your system language)
--skip-local   no local model
--skip-cloud   no cloud providers
--rollback     restore the config from the latest backup
```

On Windows, pass options through an environment variable:

```powershell
$env:FREEAGENT_ARGS = "--dry-run"; irm https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.ps1 | iex
```

On Linux, pass them after `bash -s --`:

```bash
curl -fsSL https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.sh | bash -s -- --dry-run
```

## Using it

Start Hermes with `hermes`. Switch models at any time without losing the conversation:

```
/model nemotron         # NVIDIA build
/model nemotron-ollama  # same model via Ollama Cloud
/model local            # the model on your GPU
```

The exact aliases created on your machine are listed in `freeagent-report.md`.

## Undo

Run the installer with `--rollback`. Backups live in `<Hermes folder>/freeagent-backups/`.

## Privacy

- API keys go straight into Hermes' own prompt; this tool never reads, stores or logs them.
- Reports and output mask anything that looks like a key or token.
- No telemetry. Nothing about your machine leaves it, except the test requests sent to the providers you enable.

## Limitations

- Free plans change and have limits (requests per minute, monthly quotas, one request at a time on Ollama Free).
  The probe decides what is used today; run the installer again to re-check.
- The local model has a small context window compared with cloud models.
- macOS is not supported yet.

## Development

```bash
uv run pytest -q
uv run ruff check
uv run python scripts/privacy_scan.py
```

License: MIT.
