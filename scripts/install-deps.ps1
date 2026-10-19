# Install what agent-memory needs on native Windows, from a checklist of what is missing.
#
#   scripts\install-deps.ps1            show the checklist, pick what to install
#   scripts\install-deps.ps1 -Yes       install everything missing without asking
#   scripts\install-deps.ps1 -DryRun    show the checklist and the commands, change nothing
#   scripts\install-deps.ps1 -Check     show the checklist only; exit 1 if anything is missing
#
# Uses winget (uv: astral-sh.uv, Docker Desktop: Docker.DockerDesktop, Ollama: Ollama.Ollama), then
# `uv python install 3.12` and `docker pull surrealdb/surrealdb:v3.3.4`. Every command is shown before it runs.
param([switch]$Yes, [switch]$DryRun, [switch]$Check)

$SurrealImage = 'surrealdb/surrealdb:v3.3.4'
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"   # where uv installs itself

function Has-Cmd($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
$checks = [ordered]@{
  uv      = { Has-Cmd uv }
  python  = { (Has-Cmd uv) -and ((& uv python find '>=3.12' 2>$null) -ne $null) }
  docker  = { (Has-Cmd docker) -and ((& docker version --format '{{.Server.Version}}' 2>$null) -ne $null) }
  surreal = { (Has-Cmd docker) -and ((& docker image inspect $SurrealImage 2>$null) -ne $null) }
  ollama  = { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:11434/api/version | Out-Null; $true } catch { $false } }
}
$labels = @{
  uv      = 'uv (Python package manager)'
  python  = 'Python 3.12 (installed by uv)'
  docker  = 'Docker Desktop'
  surreal = 'SurrealDB 3.3.4 image'
  ollama  = 'Ollama (GPU, port 11434), for search by meaning'
}
$commands = @{
  uv      = 'winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements'
  python  = 'uv python install 3.12'
  docker  = 'winget install --id Docker.DockerDesktop -e --accept-source-agreements --accept-package-agreements'
  surreal = "docker pull $SurrealImage"
  ollama  = 'winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements'
}

'agent-memory dependencies (Windows):'
$missing = @()
foreach ($n in $checks.Keys) {
  if (& $checks[$n]) { "  [ok]      $($labels[$n])" } else { "  [missing] $($labels[$n])"; $missing += $n }
}
if ($missing.Count -eq 0) { 'Nothing to install.'; exit 0 }
if ($Check) { exit 1 }

$pick = @{}; foreach ($n in $missing) { $pick[$n] = $true }
if (-not $Yes) {
  while ($true) {
    ''
    'Install these? Type a number to toggle it, Enter to go ahead, q to quit.'
    for ($i = 0; $i -lt $missing.Count; $i++) {
      $mark = if ($pick[$missing[$i]]) { 'x' } else { ' ' }
      "  $($i + 1). [$mark] $($labels[$missing[$i]])"
    }
    $ans = Read-Host '>'
    if ($ans -eq '') { break }
    if ($ans -eq 'q') { 'Nothing installed.'; exit 0 }
    foreach ($k in $ans -split '\s+') {
      if ($k -match '^\d+$' -and [int]$k -ge 1 -and [int]$k -le $missing.Count) { $n = $missing[[int]$k - 1]; $pick[$n] = -not $pick[$n] }
    }
  }
}

$failed = @()
foreach ($n in $checks.Keys) {
  if (-not $pick[$n]) { continue }
  ''
  "== $($labels[$n])"
  "  > $($commands[$n])"
  if ($DryRun) { continue }
  Invoke-Expression $commands[$n]
  if ($LASTEXITCODE -ne 0) { $failed += $n }
  if ($n -eq 'uv') { $env:Path = "$env:LOCALAPPDATA\Microsoft\WinGet\Links;$env:Path" }
  if ($n -eq 'docker') { '  Start Docker Desktop once (and finish its setup) before SurrealDB can be pulled.' }
}
''
if ($DryRun) { 'Dry run: nothing was changed.'; exit 0 }
if ($failed.Count) { "Failed: $($failed -join ', '). The output above says why."; exit 1 }
'Done. Open a new terminal if a command is still not found.'
