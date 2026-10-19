# Install agent-memory on Windows. First the dependencies (uv, Python, Docker Desktop, SurrealDB, Ollama):
# if any are missing it offers to install them from a checklist (scripts\install-deps.ps1). Then it
# creates the virtualenv and hands over to `agent-memory install`, which asks before each change outside
# this folder. Arguments pass through (--yes, --notes DIR, --projects DIR[,DIR], --no-service, --no-claude).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$yes = $args -contains '--yes' -or $args -contains '-y'
& .\scripts\install-deps.ps1 -Check
if ($LASTEXITCODE -ne 0) {
  ''
  if ($yes) { & .\scripts\install-deps.ps1 -Yes }
  else {
    $ans = Read-Host 'Do you want to install the missing dependencies? [y/N]'
    if ($ans -match '^(y|yes)$') { & .\scripts\install-deps.ps1 }
  }
  $env:Path = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Microsoft\WinGet\Links;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Error 'uv is required: https://docs.astral.sh/uv/getting-started/installation/'; exit 1 }
''
uv sync -q
& .\.venv\Scripts\agent-memory.exe install @args
