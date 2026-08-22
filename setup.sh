#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3.10+ is required. On Ubuntu: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "For Ubuntu/Debian install native audio dependencies with:"
  echo "  sudo apt update && sudo apt install -y ffmpeg mpv libmpv2 pulseaudio pulseaudio-utils p7zip-full"
fi

if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f config.ini ]; then
  cp config_default.ini config.ini
  echo "Created config.ini from config_default.ini. Edit server credentials before running."
fi

python locales/compile_locales.py

if ! command -v deno >/dev/null 2>&1; then
  cat <<'MSG'
Deno was not found. yt-dlp currently recommends Deno 2.3+ for full YouTube EJS support.
Install from the official Deno instructions: https://docs.deno.com/runtime/getting_started/installation/
Then reopen your shell and run: deno --version
MSG
fi

if [ ! -f TeamTalk5.py ] || [ ! -f libTeamTalk5.so ]; then
  cat <<'MSG'
TeamTalk SDK v5.22a is not installed in this project yet.
Automatic official download:
  .venv/bin/python tools/download_teamtalk_sdk.py
Or download/extract manually and run tools/install_teamtalk_sdk.py.
The official SDK binary remains subject to BearWare trial/license terms.
MSG
fi

echo "Setup finished. Run: .venv/bin/python tools/check_environment.py"
echo "Then: ./run_linux.sh"
