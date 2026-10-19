#!/usr/bin/env bash
# Install agent-memory. First the dependencies (uv, Python, Docker, SurrealDB, Ollama): if any are
# missing it offers to install them from a checklist (scripts/install-deps.sh). Then it creates the
# virtualenv and hands over to `agent-memory install`, which asks before each change outside this
# folder. Arguments pass through (--yes, --notes DIR, --projects DIR[,DIR], --no-service, --no-claude).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
yes=0
for a in "$@"; do [ "$a" = "--yes" ] || [ "$a" = "-y" ] && yes=1; done
if ! scripts/install-deps.sh --check; then
  echo
  if [ "$yes" = 1 ]; then
    scripts/install-deps.sh --yes || true
  else
    read -r -p "Do you want to install the missing dependencies? [y/N] " ans
    case "$ans" in y|Y|yes) scripts/install-deps.sh || true ;; esac
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
echo
uv sync -q
exec .venv/bin/agent-memory install "$@"
