FROM python:3.12-slim-bookworm

ARG DENO_VERSION=2.9.5
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    XDG_RUNTIME_DIR=/tmp/sntalkbot-runtime \
    TTUTIL_DATA_DIR=/app/data \
    TTUTIL_CONFIG=/app/data/config.ini \
    TTUTIL_MPV_AO=pulse

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl unzip p7zip-full ffmpeg libmpv2 pulseaudio pulseaudio-utils \
      libasound2 libpulse0 tini \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp recommends Deno for YouTube EJS challenge solving.
RUN arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) deno_asset="deno-x86_64-unknown-linux-gnu.zip" ;; \
      arm64) deno_asset="deno-aarch64-unknown-linux-gnu.zip" ;; \
      *) echo "Unsupported Deno architecture: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/${deno_asset}" -o /tmp/deno.zip; \
    unzip -q /tmp/deno.zip -d /usr/local/bin; chmod +x /usr/local/bin/deno; rm /tmp/deno.zip

RUN useradd --create-home --uid 10001 sntalkbot \
    && mkdir -p /app /app/data "$XDG_RUNTIME_DIR" \
    && chown -R sntalkbot:sntalkbot /app "$XDG_RUNTIME_DIR" \
    && chmod 700 "$XDG_RUNTIME_DIR"

WORKDIR /app
COPY --chown=sntalkbot:sntalkbot requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r /app/requirements.txt
COPY --chown=sntalkbot:sntalkbot . /app

# The official Linux TeamTalk SDK package used here is x86_64. Fail clearly on
# other architectures instead of installing an incompatible native library.
RUN test "$(dpkg --print-architecture)" = "amd64" || \
    (echo "SNTalkBot Docker image currently requires linux/amd64 because the TeamTalk v5.22a Ubuntu SDK runtime is x86_64." >&2; exit 1)

# Download official v5.22a Ubuntu 22 x86_64 TeamTalk SDK runtime at build time.
# The SDK's own trial/license terms still apply; this step does not bypass them.
RUN python /app/tools/download_teamtalk_sdk.py --platform linux-x86_64 --project /app \
    && python /app/locales/compile_locales.py \
    && python -m compileall -q /app

USER sntalkbot
VOLUME ["/app/data"]
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
