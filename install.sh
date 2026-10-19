#!/usr/bin/env bash
# Install agent-memory: checks the prerequisites, creates the virtualenv, then hands over to
# `agent-memory install`, which asks before each change outside this folder. Arguments pass through
# (--yes, --notes DIR, --projects DIR[,DIR], --no-service, --no-claude).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 ($2)" >&2; missing=1; }; }
missing=0
need uv "https://docs.astral.sh/uv/"
need git "your package manager"
command -v docker >/dev/null 2>&1 || echo "note: no docker; you will need your own SurrealDB 3.3.4 on 127.0.0.1:8000"
command -v ollama >/dev/null 2>&1 || curl -sf http://127.0.0.1:11434/api/version >/dev/null 2>&1 \
  || echo "note: no Ollama found; search will be keyword only until you install it (https://ollama.com)"
[ "$missing" = 0 ] || exit 1
uv sync -q
exec .venv/bin/agent-memory install "$@"
