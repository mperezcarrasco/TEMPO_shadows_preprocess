"""Day-by-day TEMPO cloud-shadow processing pipeline.

For a given (year, month, day), this script:

1. Discovers all L1B granules under ``{base_path}/{l1_dir_template}/year/month/day``.
2. Pairs each with its CLDO4 L2 file under ``{base_path}/{l2_dir_template}/year/month/day``.
3. Runs the DARCLOS-TEMPO vectorized algorithm (see ``shadows.py``) on every
   matched pair.
4. Writes one RGB GeoTIFF and three shapefiles (cloud / potential shadow /
   actual shadow) per granule under ``{output_root}/{year}/{month}/{day}/``.

Existing outputs are always overwritten.

Usage
-----
    python scripts/run_day.py --config configs/day_example.yaml
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
import time
from pathlib import Path

import yaml

# Allow running both as a script (``python scripts/run_day.py``) and as a module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import (
    find_matching_l2_file,
    load_l1b, load_l2,
    orient_2d, write_mask_shapefile, write_rgb_geotiff,
)
from shadows import ShadowParams, compute_masks


REQUIRED_KEYS = {
    "year", "month", "day",
    "base_path", "version",
    "l1_dir_template", "l2_dir_template",
    "l1_band",
    "cloud_threshold", "shadow_threshold",
    "safety_factor_c", "h_scale_m", "h_cap_m", "max_drop_frac",
    "output_root",
    "apply_gamma", "gamma",
}


def setup_logging(log_file: str | None = None) -> logging.Logger:
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("run_day")


def load_config(path: str) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    missing = REQUIRED_KEYS - set(cfg)
    if missing:
        raise ValueError(
            f"Config '{path}' is missing required keys: {sorted(missing)}"
        )
    cfg["year"]  = f"{int(cfg['year']):04d}"
    cfg["month"] = f"{int(cfg['month']):02d}"
    cfg["day"]   = f"{int(cfg['day']):02d}"
    return cfg


def resolve_input_dirs(cfg: dict):
    """Resolve {base_path, version, year, month, day} → (l1_dir, l2_dir)."""
    fmt = dict(
        base_path=cfg["base_path"],
        version=cfg["version"],
        year=cfg["year"], month=cfg["month"], day=cfg["day"],
    )
    l1_dir = cfg["l1_dir_template"].format(**fmt)
    l2_dir = cfg["l2_dir_template"].format(**fmt)
    return l1_dir, l2_dir


def shadow_params_from_cfg(cfg: dict) -> ShadowParams:
    return ShadowParams(
        cloud_threshold=float(cfg["cloud_threshold"]),
        shadow_threshold=float(cfg["shadow_threshold"]),
        safety_factor_c=float(cfg["safety_factor_c"]),
        h_scale_m=float(cfg["h_scale_m"]),
        h_cap_m=float(cfg["h_cap_m"]),
        max_drop_frac=float(cfg["max_drop_frac"]),
        m_earth=float(cfg.get("m_earth", 6_378_137.0)),
        n_earth=float(cfg.get("n_earth", 6_378_137.0)),
    )


def process_granule(
    l1_file: str, l2_file: str, out_dir: Path, cfg: dict,
    params: ShadowParams, logger: logging.Logger,
) -> dict:
    """Process one L1B/L2 pair; write GeoTIFF + 3 shapefiles. Return stats."""
    base = os.path.splitext(os.path.basename(l1_file))[0]
    logger.info("Processing %s", base)

    l1 = load_l1b(l1_file, cfg["l1_band"])
    l2 = load_l2(l2_file)

    cloud_mask, potential_mask, actual_mask, diag = compute_masks(
        lat=l2["lat"], lon=l2["lon"],
        cloud_fraction=l2["cloud_fraction"],
        cloud_pressure=l2["cloud_pressure"],
        surface_pressure=l2["surface_pressure"],
        terrain_height=l2["terrain_height"],
        cth_l1b=l1["cth"],
        sza=l1["sza"], saa=l1["saa"],
        vza=l1["vza"], vaa=l1["vaa"],
        params=params,
    )

    tif_path = out_dir / f"rgb_{base}.tif"
    transform, _ = write_rgb_geotiff(
        str(tif_path),
        red=l1["red"], green=l1["green"], blue=l1["blue"],
        lat=l2["lat"], lon=l2["lon"],
        apply_gamma=bool(cfg["apply_gamma"]),
        gamma=float(cfg["gamma"]),
    )

    shp_paths = {}
    src_name = os.path.basename(l1_file)
    for mask, mtype, mname, suffix in [
        (cloud_mask,     "cloud",            "Cloud",            "clouds"),
        (potential_mask, "potential_shadow", "Potential shadow", "potential_shadows"),
        (actual_mask,    "actual_shadow",    "Actual shadow",    "actual_shadows"),
    ]:
        path = out_dir / f"{base}_{suffix}.shp"
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
        "granule": base,
        "diag": diag,
        "n_cloud": int(cloud_mask.sum()),
        "n_pcsf":  int(potential_mask.sum()),
        "n_acsf":  int(actual_mask.sum()),
        "tif":     str(tif_path),
        "shp":     shp_paths,
    }


def run(cfg: dict, logger: logging.Logger) -> dict:
    l1_dir, l2_dir = resolve_input_dirs(cfg)
    out_dir = Path(cfg["output_root"]) / cfg["year"] / cfg["month"] / cfg["day"]
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Date          : %s-%s-%s", cfg["year"], cfg["month"], cfg["day"])
    logger.info("Version       : %s", cfg["version"])
    logger.info("L1B dir       : %s", l1_dir)
    logger.info("L2  dir       : %s", l2_dir)
    logger.info("Output dir    : %s", out_dir)
    logger.info(
        "Algorithm     : cloud>=%.2f  shadow<%.2f  C=%.2f  "
        "H_scale=%.0f m  H_cap=%.0f m  max_drop=%.0f%%",
        cfg["cloud_threshold"], cfg["shadow_threshold"], cfg["safety_factor_c"],
        cfg["h_scale_m"], cfg["h_cap_m"], 100.0 * cfg["max_drop_frac"],
    )

    l1_files = sorted(glob.glob(os.path.join(l1_dir, "*.nc")))
    if not l1_files:
        raise FileNotFoundError(f"No L1B .nc files found in {l1_dir}")
    logger.info("Found %d L1B granule(s)", len(l1_files))

    params = shadow_params_from_cfg(cfg)
    stats = []
    n_no_l2 = 0
    n_failed = 0
    t0 = time.time()

    for idx, l1_file in enumerate(l1_files, 1):
        logger.info("[%d/%d] %s", idx, len(l1_files), os.path.basename(l1_file))
        l2_file = find_matching_l2_file(l1_file, l2_dir, cfg["version"])
        if l2_file is None:
            logger.warning("  No matching L2 %s file in %s — skipping",
                           cfg["version"], l2_dir)
            n_no_l2 += 1
            continue
        try:
            stats.append(process_granule(
                l1_file, l2_file, out_dir, cfg, params, logger,
            ))
        except Exception as e:
            logger.error("  FAILED: %s", e, exc_info=True)
            n_failed += 1

    elapsed = time.time() - t0
    summary = {
        "n_l1": len(l1_files),
        "n_processed": len(stats),
        "n_no_l2": n_no_l2,
        "n_failed": n_failed,
        "elapsed_s": elapsed,
        "stats": stats,
    }
    logger.info(
        "Done in %.1fs. processed=%d  no_l2=%d  failed=%d",
        elapsed, summary["n_processed"], n_no_l2, n_failed,
    )
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Run the DARCLOS-TEMPO pipeline for one day."
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to a YAML config file.",
    )
    parser.add_argument(
        "--log-file", default=None,
        help="Optional path to a log file (in addition to stdout).",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    logger = setup_logging(args.log_file)
    logger.info("Config: %s", args.config)
    run(cfg, logger)


if __name__ == "__main__":
    main()
