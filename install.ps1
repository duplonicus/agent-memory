# Install agent-memory on Windows: checks the prerequisites, creates the virtualenv, then hands over to
# `agent-memory install`, which asks before each change outside this folder. Arguments pass through.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Error 'missing: uv (https://docs.astral.sh/uv/)'; exit 1 }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { 'note: no docker; you will need your own SurrealDB 3.3.4 on 127.0.0.1:8000' }
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:11434/api/version | Out-Null }
catch { 'note: Ollama is not answering; search will be keyword only until you install it (https://ollama.com)' }
uv sync -q
& .\.venv\Scripts\agent-memory.exe install @args
