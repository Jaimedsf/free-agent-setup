#!/usr/bin/env bash
# free-agent-setup bootstrap for Linux.
# Usage: curl -fsSL https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.sh | bash
# Pass options with: ... | bash -s -- --dry-run   (use a local clone: FREEAGENT_SRC=<folder>)
set -euo pipefail
repo="https://github.com/Jaimedsf/free-agent-setup/archive/refs/heads/main.tar.gz"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (https://astral.sh/uv) ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

here="${FREEAGENT_SRC:-}"
if [ -z "$here" ] && [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$here" ] && grep -q 'name = "freeagent"' "$here/pyproject.toml" 2>/dev/null; then
    project="$here"
else
    tmp="$(mktemp -d)"
    curl -fsSL "$repo" | tar -xz -C "$tmp"
    project="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
fi

# Under `curl | bash` stdin is the exhausted pipe: give prompts the terminal back.
if [ ! -t 0 ] && { true </dev/tty; } 2>/dev/null; then
    exec uv run --quiet --project "$project" python -m freeagent "$@" </dev/tty
fi
exec uv run --quiet --project "$project" python -m freeagent "$@"
