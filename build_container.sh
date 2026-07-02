#!/usr/bin/env bash
# Build the DARCLOS-TEMPO container image.
#
# Usage: bash build_container.sh
set -euo pipefail

IMAGE_NAME="${DARCLOS_TEMPO_IMAGE:-darclos-tempo}"
IMAGE_TAG="${DARCLOS_TEMPO_TAG:-latest}"

docker build \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    -f Dockerfile \
    .

echo
echo "Built image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "Next: bash run_container.sh <path-to-TEMPO-archive> [<path-to-output-root>]"
