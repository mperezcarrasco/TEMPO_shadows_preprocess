#!/usr/bin/env bash
# Run the DARCLOS-TEMPO container.
#
# Usage:
#   bash run_container.sh <archive-path> [<output-path>] [-- extra docker args]
#
#   <archive-path>  Host directory that contains the TEMPO L1B/L2 tree
#                   (mounted read-only at /data inside the container).
#   <output-path>   Host directory where GeoTIFFs and shapefiles will be
#                   written (mounted read/write at /outputs). Optional;
#                   defaults to ./results next to this script.
#
# The container is CPU-only, non-privileged, and drops you into an
# interactive shell with the pipeline code at /app.
#
# Inside the container:
#   python3 scripts/run_scan.py --config configs/my_day.yaml
#
# Point `base_path` in your YAML at /data and `output_root` at /outputs.

set -euo pipefail

IMAGE_NAME="${DARCLOS_TEMPO_IMAGE:-darclos-tempo}"
IMAGE_TAG="${DARCLOS_TEMPO_TAG:-latest}"

if [[ $# -lt 1 ]]; then
    echo "Usage: bash run_container.sh <archive-path> [<output-path>]"
    exit 1
fi

ARCHIVE="$(cd "$1" && pwd)"
shift

if [[ $# -ge 1 && "$1" != "--" ]]; then
    OUTPUTS="$(mkdir -p "$1" && cd "$1" && pwd)"
    shift
else
    OUTPUTS="$(mkdir -p "$(pwd)/results" && cd "$(pwd)/results" && pwd)"
fi

# Consume the -- separator if present so remaining $@ are passed to docker.
if [[ $# -ge 1 && "$1" == "--" ]]; then
    shift
fi

echo "Archive : ${ARCHIVE}  →  /data (read-only)"
echo "Outputs : ${OUTPUTS}  →  /outputs"
echo "Image   : ${IMAGE_NAME}:${IMAGE_TAG}"
echo

docker run -it --rm \
    --name darclos-tempo \
    --mount "type=bind,src=${ARCHIVE},dst=/data,readonly" \
    --mount "type=bind,src=${OUTPUTS},dst=/outputs" \
    "$@" \
    "${IMAGE_NAME}:${IMAGE_TAG}" \
    bash
