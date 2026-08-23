#!/usr/bin/env bash
set -euo pipefail
SINK_NAME="${TTUTIL_PULSE_SINK:-sntalkbot}"
SINK_DESC="${TTUTIL_PULSE_DESC:-SNTalkBot_Virtual_Output}"

if ! command -v pulseaudio >/dev/null 2>&1 || ! command -v pactl >/dev/null 2>&1; then
  echo "PulseAudio and pactl are required." >&2
  exit 1
fi

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/sntalkbot-runtime-${UID}}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

pulseaudio --check >/dev/null 2>&1 || pulseaudio --daemonize=yes --exit-idle-time=-1 --log-target=stderr
for _ in $(seq 1 30); do
  pactl info >/dev/null 2>&1 && break
  sleep 0.1
done

if ! pactl list short sinks | awk '{print $2}' | grep -Fxq "$SINK_NAME"; then
  pactl load-module module-null-sink sink_name="$SINK_NAME" sink_properties="device.description=$SINK_DESC" rate=48000 channels=2 >/dev/null
fi
pactl set-default-sink "$SINK_NAME"
pactl set-default-source "${SINK_NAME}.monitor"

echo "PulseAudio bridge ready."
echo "Default sink: $SINK_NAME"
echo "Default source: ${SINK_NAME}.monitor"
