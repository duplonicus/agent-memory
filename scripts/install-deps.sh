#!/usr/bin/env bash
# Install what agent-memory needs, from a checklist of what is missing on this machine.
#
#   scripts/install-deps.sh            show the checklist, pick what to install
#   scripts/install-deps.sh --yes      install everything missing without asking
#   scripts/install-deps.sh --dry-run  show the checklist and the commands, change nothing
#   scripts/install-deps.sh --check    show the checklist only; exit 1 if anything is missing
#
# Linux and WSL2. Every command is the vendor's own documented one, shown before it runs:
#   uv       https://docs.astral.sh/uv/getting-started/installation/
#   Python   uv python install 3.12
#   Docker   https://docs.docker.com/engine/install/ (convenience script) + linux-postinstall (docker group)
#   SurrealDB docker pull surrealdb/surrealdb:v3.3.4
#   Ollama   Linux: https://docs.ollama.com/linux ; WSL: the Windows app via winget (Ollama.Ollama), on its
#            default port 11434 (same speed as Ollama inside WSL, measured: docs/BENCHMARKS.md)
set -uo pipefail

YES=0; DRY=0; CHECK=0
for a in "$@"; do
  case "$a" in
    --yes|-y) YES=1 ;;
    --dry-run) DRY=1 ;;
    --check) CHECK=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
  esac
done

SURREAL_IMAGE="surrealdb/surrealdb:v3.3.4"
OLLAMA_URL="http://127.0.0.1:11434/api/version"
WSL=0
grep -qi microsoft /proc/version 2>/dev/null && WSL=1
if [ "$(uname -s)" != "Linux" ]; then
  echo "install-deps.sh is for Linux and WSL2. On macOS install uv, Docker Desktop and Ollama from their sites;"
  echo "on Windows run scripts\\install-deps.ps1."
  exit 1
fi
export PATH="$HOME/.local/bin:$PATH"   # where the uv installer puts uv

has_uv()      { command -v uv >/dev/null 2>&1; }
has_python()  { has_uv && uv python find '>=3.12' >/dev/null 2>&1; }
has_docker()  { command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; }
has_surreal() { has_docker && docker image inspect "$SURREAL_IMAGE" >/dev/null 2>&1; }
has_ollama()  { curl -sf --max-time 3 "$OLLAMA_URL" >/dev/null 2>&1; }

run() {  # show, then run (or only show on --dry-run)
  echo "  \$ $*"
  [ "$DRY" = 1 ] && return 0
  bash -c "$*"
}

# Commands that need sudo, when there is no terminal to type a password into (an agent running this):
# printed at the end for the person to run themselves, instead of failing half-way.
FOR_YOU=()
root() {
  if [ "$DRY" = 1 ] || [ -t 0 ] || sudo -n true 2>/dev/null; then
    run "$*"
  else
    echo "  needs your password, saved for the end: $*"
    FOR_YOU+=("$*")
  fi
}

install_uv()     { run "curl -LsSf https://astral.sh/uv/install.sh | sh"; }
install_python() { run "uv python install 3.12"; }
install_docker() {
  if [ "$WSL" = 1 ] && [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
    echo "  Docker Desktop is installed on Windows: turn on Settings > Resources > WSL integration for this distro"
    echo "  instead of installing a second Docker inside WSL. Skipping."
    return 0
  fi
  run "curl -fsSL https://get.docker.com -o /tmp/get-docker.sh"
  root "sudo sh /tmp/get-docker.sh"
  root "sudo usermod -aG docker ${USER:-$(id -un)}"
  if [ -d /run/systemd/system ]; then
    root "sudo systemctl enable --now docker.service containerd.service"
  else
    echo "  systemd is not running, so Docker won't start on its own. In WSL, add [boot] systemd=true to /etc/wsl.conf."
  fi
  echo "  Log out and back in (in WSL: wsl.exe --shutdown, then reopen) so the docker group applies."
}
install_surreal() {
  if [ "${#FOR_YOU[@]}" -gt 0 ]; then
    FOR_YOU+=("docker pull $SURREAL_IMAGE"); echo "  waits for Docker: saved for the end"; return 0
  fi
  run "docker pull $SURREAL_IMAGE || sudo -n docker pull $SURREAL_IMAGE"
}
install_ollama() {
  if [ "$WSL" = 1 ]; then
    if ! command -v winget.exe >/dev/null 2>&1; then
      echo "  winget is not reachable from WSL; install Ollama for Windows from https://ollama.com/download"
      return 0
    fi
    # winget runs on the Windows side; cd to a Windows folder so it does not start in a \\wsl$ path.
    run "cd /mnt/c && winget.exe install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements"
    mode=$(wslinfo --networking-mode 2>/dev/null || echo unknown)
    if [ "$mode" != "mirrored" ]; then
      echo "  WSL networking is '$mode', so WSL cannot reach Windows' Ollama at 127.0.0.1."
      echo "  Turn on mirrored networking: add networkingMode=mirrored under [wsl2] in %UserProfile%\\.wslconfig,"
      echo "  run wsl.exe --shutdown, reopen. (Windows 11 22H2 or later.)"
    fi
  else
    run "curl -fsSL https://ollama.com/install.sh | sh"
  fi
}

NAMES=(uv python docker surreal ollama)
declare -A LABEL=(
  [uv]="uv (Python package manager)"
  [python]="Python 3.12 (installed by uv)"
  [docker]="Docker Engine$( [ "$WSL" = 1 ] && echo ' inside WSL')"
  [surreal]="SurrealDB 3.3.4 image"
  [ollama]="Ollama$( [ "$WSL" = 1 ] && echo ' for Windows (GPU, port 11434)' || echo ' (port 11434)'), for search by meaning"
)

missing=()
echo "agent-memory dependencies ($( [ "$WSL" = 1 ] && echo WSL2 || echo Linux )):"
for n in "${NAMES[@]}"; do
  if "has_$n"; then
    printf '  [ok]      %s\n' "${LABEL[$n]}"
  else
    printf '  [missing] %s\n' "${LABEL[$n]}"
    missing+=("$n")
  fi
done
if [ "${#missing[@]}" = 0 ]; then
  echo "Nothing to install."
  exit 0
fi
[ "$CHECK" = 1 ] && exit 1

declare -A PICK
for n in "${missing[@]}"; do PICK[$n]=1; done
if [ "$YES" = 0 ] && [ -t 0 ]; then
  while :; do
    echo
    echo "Install these? Type a number to toggle it, Enter to go ahead, q to quit."
    i=1
    for n in "${missing[@]}"; do
      printf '  %d. [%s] %s\n' "$i" "$( [ "${PICK[$n]}" = 1 ] && echo x || echo ' ')" "${LABEL[$n]}"
      i=$((i + 1))
    done
    read -r -p "> " ans
    case "$ans" in
      "") break ;;
      q|Q) echo "Nothing installed."; exit 0 ;;
      *)
        for k in $ans; do
          if [[ "$k" =~ ^[0-9]+$ ]] && [ "$k" -ge 1 ] && [ "$k" -le "${#missing[@]}" ]; then
            n=${missing[$((k - 1))]}
            PICK[$n]=$((1 - PICK[$n]))
          fi
        done ;;
    esac
  done
elif [ "$YES" = 0 ]; then
  echo "No terminal to ask on; rerun with --yes to install everything missing."
  exit 1
fi

failed=()
for n in "${NAMES[@]}"; do
  [ "${PICK[$n]:-0}" = 1 ] || continue
  echo
  echo "== ${LABEL[$n]}"
  "install_$n" || failed+=("$n")
done
echo
[ "$DRY" = 1 ] && { echo "Dry run: nothing was changed."; exit 0; }
if [ "${#FOR_YOU[@]}" -gt 0 ]; then
  echo "These need your password, so run them yourself (in Claude Code, prefix each with ! ):"
  printf '  %s\n' "${FOR_YOU[@]}"
  echo "Then log out and back in (WSL: wsl.exe --shutdown) so the docker group applies."
  echo
fi
if [ "${#failed[@]}" -gt 0 ]; then
  echo "Failed: ${failed[*]}. The output above says why."
  exit 1
fi
echo "Done. Open a new terminal if a command is still not found (uv adds itself to ~/.local/bin)."
