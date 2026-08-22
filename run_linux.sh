#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export LD_LIBRARY_PATH="$PWD:${LD_LIBRARY_PATH:-}"
export TTUTIL_DATA_DIR="${TTUTIL_DATA_DIR:-$PWD/data}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/sntalkbot-runtime-${UID}}"
export TTUTIL_MPV_AO="${TTUTIL_MPV_AO:-pulse}"
mkdir -p "$TTUTIL_DATA_DIR" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# On a headless Linux server MPV plays into a PulseAudio null sink and TeamTalk
# captures that sink's monitor source. Set TTUTIL_AUTO_PULSE=0 to manage audio
# routing yourself.
if [ "${TTUTIL_AUTO_PULSE:-1}" != "0" ]; then
  "$PWD/tools/setup_pulse_bridge.sh"
fi

CONFIG="${TTUTIL_CONFIG:-$PWD/config.ini}"
if [ ! -f "$CONFIG" ]; then
  cp config_default.ini "$CONFIG"
  echo "Created $CONFIG. Edit TeamTalk server credentials before normal use." >&2
fi
exec "${PYTHON:-python3}" main.py -f "$CONFIG" "$@"
