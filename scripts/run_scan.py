"""Scan-by-scan TEMPO cloud-shadow processing pipeline.

Variant of :mod:`run_day`. Instead of processing each granule independently,
this script discovers all granules for a given (year, month, day), groups
them by scan number, concatenates the L1B + L2 arrays of each scan along the
``mirror_step`` axis, and runs the DARCLOS-TEMPO algorithm **once per scan**
on the merged grid.

Two motivations for merging at the L1B/L2 level rather than mosaicking the
per-granule outputs after the fact:

1. **Cross-boundary shadow projection.** A cloud near the eastern edge of
   one granule can cast a shadow that lands inside the next granule. The
   per-granule pipeline necessarily misses those — the scan-level pipeline
   sees the full footprint and detects them correctly.
2. **Whole-scan validity guard.** The ``max_drop_frac`` height-validity
   threshold is evaluated over the full scan, so a single granule with many
   bad cloud-pressure retrievals can no longer fail the whole day.

Usage
-----
    python scripts/run_scan.py --config configs/day_example.yaml

Reads the same YAML schema as ``run_day.py``. Outputs are written to
``{output_root}_scan/{year}/{month}/{day}/`` (the script appends ``_scan`` to
the ``output_root`` from the config). Per scan, the following files are
produced:

- ``rgb_S<scan>.tif``                 (3-band uint8 GeoTIFF)
- ``S<scan>_clouds.shp``              (cloud polygons)
- ``S<scan>_potential_shadows.shp``   (PCSF polygons)
- ``S<scan>_actual_shadows.shp``      (ACSF polygons)

Nothing in ``shadows.py`` or ``io_utils.py`` is modified — this script only
reorders inputs to those existing functions.
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# Allow running both as a script and as a module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the helpers from run_day without modifying it.
from run_day import (
    load_config,
    resolve_input_dirs,
    setup_logging,
    shadow_params_from_cfg,
)
from io_utils import (
    find_matching_l2_file,
    load_l1b, load_l2,
    orient_2d, write_mask_shapefile, write_rgb_geotiff,
)
from shadows import ShadowParams, compute_masks


SCAN_RE = re.compile(r"_S(\d{3})G(\d{2})")

# L1B fields we concatenate per scan (must match keys returned by io_utils.load_l1b).
_L1_KEYS = ("red", "green", "blue", "cth", "sza", "saa", "vza", "vaa")
# L2 fields we concatenate per scan (must match keys returned by io_utils.load_l2).
_L2_KEYS = ("lat", "lon", "cloud_fraction", "cloud_pressure",
            "terrain_height", "surface_pressure")


def scan_output_dir(cfg: dict) -> Path:
    """{output_root}_scan/{year}/{month}/{day}/ — same shape as run_day's output."""
    return (
        Path(str(cfg["output_root"]) + "_scan")
        / cfg["year"] / cfg["month"] / cfg["day"]
    )


def group_l1_files_by_scan(
    l1_files: List[str], l2_dir: str, version: str,
    logger: logging.Logger,
) -> Tuple[Dict[str, List[Tuple[str, str, str]]], List[str]]:
    """Pair every L1B file with its L2 and group the pairs by scan number.

    Returns
    -------
    by_scan : {scan: [(granule, l1_file, l2_file), ...]} sorted by granule.
    no_l2   : list of L1B files for which no matching L2 was found.
    """
    by_scan: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    no_l2: List[str] = []
    for l1 in l1_files:
        m = SCAN_RE.search(os.path.basename(l1))
        if not m:
            logger.warning("Unparseable filename, skipping: %s", l1)
            continue
        scan, granule = m.group(1), m.group(2)
        l2 = find_matching_l2_file(l1, l2_dir, version)
        if l2 is None:
            no_l2.append(l1)
            continue
        by_scan[scan].append((granule, l1, l2))
    for scan in by_scan:
        by_scan[scan].sort(key=lambda x: x[0])
    return dict(by_scan), no_l2


def load_and_concat_scan(
    granules: List[Tuple[str, str, str]],
    band: str,
    logger: logging.Logger,
) -> Tuple[dict, List[Tuple[str, int, int]]]:
    """Load every granule in a scan and concatenate the arrays along mirror_step.

    Returns
    -------
    merged : dict with the same keys as ``load_l1b`` ∪ ``load_l2``, each array
        having shape ``(sum of per-granule mirror_step, 2048)``.
    breaks : list of ``(granule, row_start, row_end)`` for diagnostic logging.

    Raises
    ------
    ValueError if no granule could be loaded.
    """
    l1_dicts: List[dict] = []
    l2_dicts: List[dict] = []
    breaks: List[Tuple[str, int, int]] = []
    cursor = 0

    for granule, l1_file, l2_file in granules:
        try:
            l1 = load_l1b(l1_file, band)
            l2 = load_l2(l2_file)
        except Exception as e:
            logger.warning("  G%s: load failed (%s) — skipping granule", granule, e)
            continue

        n_rows = l1["red"].shape[0]
        if l2["lat"].shape[0] != n_rows:
            logger.warning(
                "  G%s: L1B and L2 mirror_step mismatch (%d vs %d) — skipping",
                granule, n_rows, l2["lat"].shape[0],
            )
            continue

        l1_dicts.append(l1)
        l2_dicts.append(l2)
        breaks.append((granule, cursor, cursor + n_rows))
        cursor += n_rows

    if not l1_dicts:
        raise ValueError("no granules could be loaded for this scan")

    merged = {}
    for k in _L1_KEYS:
        merged[k] = np.concatenate([d[k] for d in l1_dicts], axis=0)
    for k in _L2_KEYS:
        merged[k] = np.concatenate([d[k] for d in l2_dicts], axis=0)

    # Sanity check: every concatenated array must have the same mirror_step extent.
    n_ref = merged["red"].shape[0]
    for k, arr in merged.items():
        if arr.shape[0] != n_ref:
            raise ValueError(
                f"concatenation produced inconsistent mirror_step for '{k}': "
                f"{arr.shape[0]} != {n_ref}"
            )
    return merged, breaks


def process_scan(
    scan: str,
    granules: List[Tuple[str, str, str]],
    out_dir: Path, cfg: dict,
    params: ShadowParams, logger: logging.Logger,
) -> dict:
    """Concatenate all granules of one scan, run DARCLOS, write outputs."""
    logger.info("Scan S%s : %d granule(s) %s",
                scan, len(granules), [g for g, _, _ in granules])

    merged, breaks = load_and_concat_scan(granules, cfg["l1_band"], logger)
    n_rows, n_cols = merged["red"].shape
    logger.info("  merged grid: %d × %d   granule boundaries: %s",
                n_rows, n_cols,
                ", ".join(f"G{g}:[{a}:{b}]" for g, a, b in breaks))

    cloud_mask, potential_mask, actual_mask, diag = compute_masks(
        lat=merged["lat"], lon=merged["lon"],
        cloud_fraction=merged["cloud_fraction"],
        cloud_pressure=merged["cloud_pressure"],
        surface_pressure=merged["surface_pressure"],
        terrain_height=merged["terrain_height"],
        cth_l1b=merged["cth"],
        sza=merged["sza"], saa=merged["saa"],
        vza=merged["vza"], vaa=merged["vaa"],
        params=params,
    )

    tif_path = out_dir / f"rgb_S{scan}.tif"
    transform, _ = write_rgb_geotiff(
        str(tif_path),
        red=merged["red"], green=merged["green"], blue=merged["blue"],
        lat=merged["lat"], lon=merged["lon"],
        apply_gamma=bool(cfg["apply_gamma"]),
        gamma=float(cfg["gamma"]),
    )

    shp_paths = {}
    src_name = f"S{scan}"
    for mask, mtype, mname, suffix in [
        (cloud_mask,     "cloud",            "Cloud",            "clouds"),
        (potential_mask, "potential_shadow", "Potential shadow", "potential_shadows"),
        (actual_mask,    "actual_shadow",    "Actual shadow",    "actual_shadows"),
    ]:
        path = out_dir / f"S{scan}_{suffix}.shp"
        result = write_mask_shapefile(
            str(path), orient_2d(mask), transform, mtype, mname, src_name,
        )
        shp_paths[suffix] = result if result is not None else "(no features)"

    logger.info(
        "  source=%d  height_dropped=%d  angle_dropped=%d  "
        "cloud=%d  pcsf=%d  acsf=%d",
        diag["n_source"], diag["n_dropped_height"], diag["n_dropped_angles"],
        int(cloud_mask.sum()), int(potential_mask.sum()), int(actual_mask.sum()),
    )
    return {
        "scan":        scan,
        "n_granules":  len(granules),
        "shape":       (int(n_rows), int(n_cols)),
        "diag":        diag,
        "n_cloud":     int(cloud_mask.sum()),
        "n_pcsf":      int(potential_mask.sum()),
        "n_acsf":      int(actual_mask.sum()),
        "tif":         str(tif_path),
        "shp":         shp_paths,
    }


def run(cfg: dict, logger: logging.Logger) -> dict:
    l1_dir, l2_dir = resolve_input_dirs(cfg)
    out_dir = scan_output_dir(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Date          : %s-%s-%s", cfg["year"], cfg["month"], cfg["day"])
    logger.info("Version       : %s", cfg["version"])
    logger.info("L1B dir       : %s", l1_dir)
    logger.info("L2  dir       : %s", l2_dir)
    logger.info("Output dir    : %s", out_dir)
    logger.info(
        "Algorithm     : cloud>=%.2f  shadow<%.2f  C=%.2f  "
        "H_scale=%.0f m  H_cap=%.0f m  max_drop=%.0f%% (per scan)",
        cfg["cloud_threshold"], cfg["shadow_threshold"], cfg["safety_factor_c"],
        cfg["h_scale_m"], cfg["h_cap_m"], 100.0 * cfg["max_drop_frac"],
    )

    l1_files = sorted(glob.glob(os.path.join(l1_dir, "*.nc")))
    if not l1_files:
        raise FileNotFoundError(f"No L1B .nc files found in {l1_dir}")

    by_scan, no_l2 = group_l1_files_by_scan(l1_files, l2_dir, cfg["version"], logger)
    logger.info("Found %d L1B granule(s) → %d scan(s)", len(l1_files), len(by_scan))
    if no_l2:
        logger.warning("%d granule(s) without matching L2 — skipping", len(no_l2))

    params = shadow_params_from_cfg(cfg)
    stats = []
    n_failed = 0
    t0 = time.time()

    for idx, scan in enumerate(sorted(by_scan), 1):
        logger.info("[%d/%d] scan S%s", idx, len(by_scan), scan)
        try:
            stats.append(process_scan(
                scan, by_scan[scan], out_dir, cfg, params, logger,
            ))
        except Exception as e:
            logger.error("  FAILED: %s", e, exc_info=True)
            n_failed += 1

    elapsed = time.time() - t0
    summary = {
        "n_l1":         len(l1_files),
        "n_scans":      len(by_scan),
        "n_processed":  len(stats),
        "n_failed":     n_failed,
        "n_no_l2":      len(no_l2),
        "elapsed_s":    elapsed,
        "stats":        stats,
    }
    logger.info(
        "Done in %.1fs. scans_processed=%d  scans_failed=%d  granules_no_l2=%d",
        elapsed, len(stats), n_failed, len(no_l2),
    )
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Run the DARCLOS-TEMPO pipeline per scan (granules merged "
                    "at the L1B/L2 level before the algorithm runs).",
    )
    parser.add_argument(
        "--config", required=True, help="Path to a YAML config file.",
    )
    parser.add_argument(
        "--log-file", default=None,
        help="Optional path to a log file (in addition to stdout).",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    logger = setup_logging(args.log_file)
    logger.info("Config: %s   mode: scan-level", args.config)
    run(cfg, logger)


if __name__ == "__main__":
    main()
