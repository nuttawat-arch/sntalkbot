#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

IMAGE_REPO="${TTU_IMAGE_REPO:-nuttawat0295/sntalkbot}"
IMAGE_TAG="${TTU_TAG:-latest}"
IMAGE_NAME="${IMAGE_REPO}:${IMAGE_TAG}"
PLATFORM="${TTU_PLATFORM:-linux/amd64}"

command -v docker >/dev/null 2>&1 || { echo "Docker is required." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable or this user cannot access it." >&2; exit 1; }

echo "Building $IMAGE_NAME for $PLATFORM ..."
docker build --platform "$PLATFORM" -t "$IMAGE_NAME" .

echo "Pushing $IMAGE_NAME to Docker Hub ..."
docker push "$IMAGE_NAME"

echo "Published: $IMAGE_NAME"
