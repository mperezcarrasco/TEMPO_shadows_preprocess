# =============================================================================
# DARCLOS-TEMPO — reproducible runtime image
#
# Slim Debian base with GDAL/PROJ preinstalled (~500 MB uncompressed).
# CPU-only; no CUDA, no Jupyter, no PyTorch.
#
# Build:  bash build_container.sh
# Run:    bash run_container.sh /path/to/TEMPO_archive
# =============================================================================

FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.4

# ---- System-level Python + pip -----------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ---- Python deps (pinned in requirements.txt) --------------------------------
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages \
        -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# ---- Pipeline code -----------------------------------------------------------
WORKDIR /app
COPY scripts/  /app/scripts/
COPY configs/  /app/configs/

# ---- Runtime configuration ---------------------------------------------------
# HDF5 file-locking off — required on many shared/NFS storage setups.
ENV HDF5_USE_FILE_LOCKING=FALSE
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default: print the scan-mode CLI help. Users pass an explicit command instead:
#   docker run ... run_scan.py --config configs/day.yaml
CMD ["python3", "scripts/run_scan.py", "--help"]
