#!/usr/bin/env bash
set -euo pipefail
cd /app
export LD_LIBRARY_PATH="/app:${LD_LIBRARY_PATH:-}"
export TTUTIL_DATA_DIR="${TTUTIL_DATA_DIR:-/app/data}"
export TTUTIL_CONFIG="${TTUTIL_CONFIG:-$TTUTIL_DATA_DIR/config.ini}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/sntalkbot-runtime}"
export TTUTIL_MPV_AO="${TTUTIL_MPV_AO:-pulse}"
mkdir -p "$TTUTIL_DATA_DIR"
if [ ! -f "$TTUTIL_CONFIG" ]; then
  cp /app/config_default.ini "$TTUTIL_CONFIG"
  echo "Created $TTUTIL_CONFIG from config_default.ini" >&2
fi
# Preserve the legacy project default cookie behavior without overwriting a
# user-supplied persistent cookie. The bundled default is only a bootstrap;
# TTUHelper cks can replace /app/data/cookies.txt later using the same path.
RUNTIME_COOKIES="${SNTALKBOT_COOKIES_FILE:-$TTUTIL_DATA_DIR/cookies.txt}"
DEFAULT_COOKIES="/app/defaults/cookies.txt"
if [ ! -f "$RUNTIME_COOKIES" ] && [ -f "$DEFAULT_COOKIES" ]; then
  cp "$DEFAULT_COOKIES" "$RUNTIME_COOKIES"
  chmod 600 "$RUNTIME_COOKIES" 2>/dev/null || true
  echo "Initialized default YouTube cookies at $RUNTIME_COOKIES" >&2
fi
/app/tools/setup_pulse_bridge.sh
exec python3 /app/main.py -f "$TTUTIL_CONFIG" "$@"
