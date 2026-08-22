#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

DENO_VERSION="${DENO_VERSION:-2.9.5}"
PYTHON="${PYTHON:-python3}"

say() { printf '\n==> %s\n' "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

if [[ "$(uname -s)" != "Linux" ]]; then
  fail "install.sh is intended for Linux. Use setup.bat on Windows."
fi

if [[ -r /etc/os-release ]]; then
  . /etc/os-release
else
  fail "Cannot detect Linux distribution (/etc/os-release missing)."
fi

if [[ "${ID:-}" != "ubuntu" && "${ID:-}" != "debian" ]]; then
  fail "Automatic one-command install currently supports Ubuntu/Debian only (detected: ${ID:-unknown})."
fi

SUDO=""
if [[ "$EUID" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || fail "sudo is required to install system packages."
  SUDO="sudo"
fi

say "Installing Linux system dependencies"
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
  ca-certificates curl unzip p7zip-full ffmpeg mpv libmpv2 \
  pulseaudio pulseaudio-utils python3 python3-venv python3-pip

if ! command -v deno >/dev/null 2>&1; then
  say "Installing Deno ${DENO_VERSION} for yt-dlp EJS support"
  arch="$(dpkg --print-architecture)"
  case "$arch" in
    amd64) deno_asset="deno-x86_64-unknown-linux-gnu.zip" ;;
    arm64) deno_asset="deno-aarch64-unknown-linux-gnu.zip" ;;
    *) fail "Unsupported Deno architecture: $arch" ;;
  esac
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  curl -fL "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/${deno_asset}" -o "$tmpdir/deno.zip"
  unzip -q "$tmpdir/deno.zip" -d "$tmpdir"
  $SUDO install -m 0755 "$tmpdir/deno" /usr/local/bin/deno
  rm -rf "$tmpdir"
  trap - EXIT
fi

say "Creating Python environment and installing Python dependencies"
./setup.sh

say "Installing official TeamTalk SDK runtime files"
.venv/bin/python tools/download_teamtalk_sdk.py

say "Compiling locales"
.venv/bin/python locales/compile_locales.py

say "Checking runtime environment"
.venv/bin/python tools/check_environment.py

say "Validating project"
.venv/bin/python tools/validate_project.py

cat <<'MSG'

Installation finished successfully.

Next steps:
  1. Edit config.ini and enter your TeamTalk server/account settings.
  2. Run the bot with: ./run_linux.sh

The installer is safe to run again after an update. Existing config.ini is not overwritten.
MSG
