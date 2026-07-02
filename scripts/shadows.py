"""Vectorized DARCLOS-TEMPO shadow projection.

Mirrors the algorithm in `notebooks/Cloud_Shadows_v3_vectorized.ipynb`. Pure
NumPy / SciPy — no I/O. Inputs are arrays in the native (mirror_step, xtrack)
layout; outputs are arrays in the same layout.

References
----------
Trees, V. J. H., Wang, P., & Stammes, P. (2022). DARCLOS: a cloud shadow
detection algorithm for TROPOMI. Atmospheric Measurement Techniques, 15,
3121-3140. doi:10.5194/amt-15-3121-2022.

Wang, H., et al. (2025). Algorithm Theoretical Basis for Version 3 TEMPO
O2-O2 Cloud Product. Earth and Space Science, 12, e2024EA004165.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class ShadowParams:
    """All DARCLOS-TEMPO algorithm parameters in one immutable container."""

    cloud_threshold:  float   # ECF >= this → cloud-source / cloud-class pixel
    shadow_threshold: float   # ECF <  this & PCSF → actual shadow (ACSF surrogate)
    safety_factor_c:  float   # Trees et al. (2022) Eq. 1
    h_scale_m:        float   # hypsometric scale height [m]
    h_cap_m:          float   # max physical cloud altitude [m]
    max_drop_frac:    float   # fail if more than this fraction of sources are dropped
    m_earth:          float = 6_378_137.0
    n_earth:          float = 6_378_137.0


def compute_heights_vectorized(
    cth:   np.ndarray,
    p_cld: np.ndarray,
    p_sfc: np.ndarray,
    h_sfc: np.ndarray,
    params: ShadowParams,
) -> np.ndarray:
    """Effective shadow-projection height (above terrain), in meters.

    Returns an array the same shape as the inputs, with NaN where neither L1B
    `cloud_top_height` nor the hypsometric fallback yields a physical value.

    Per-pixel priority:
        1. L1B CTH (ASL) when finite and above terrain.
        2. Hypsometric: ``H_SCALE * ln(p_sfc / p_cloud) + terrain``, capped at
           ``H_CAP_M`` ASL, with safety factor ``C`` applied to above-terrain
           height.
        3. Cloud at/below surface (``p_sfc <= p_cloud``): h_eff = 0 (no shadow).
    """
    b1 = np.isfinite(cth) & (cth > h_sfc)
    h_asl_b1 = np.where(b1, np.minimum(cth, params.h_cap_m), np.nan)
    h_eff_b1 = (1.0 + params.safety_factor_c) * (h_asl_b1 - h_sfc)

    p_finite = (
        np.isfinite(p_cld) & np.isfinite(p_sfc) & (p_cld > 0) & (p_sfc > 0)
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        h_above = params.h_scale_m * np.log(p_sfc / p_cld)
    use_b2 = (
        p_finite & (p_sfc > p_cld) & np.isfinite(h_above) & (h_above > 0)
    )
    h_asl_b2 = np.where(
        use_b2, np.minimum(h_above + h_sfc, params.h_cap_m), np.nan
    )
    h_eff_b2 = (1.0 + params.safety_factor_c) * (h_asl_b2 - h_sfc)

    below_sfc = p_finite & (p_sfc <= p_cld)

    h_eff = np.full_like(h_eff_b1, np.nan)
    h_eff = np.where(b1, h_eff_b1, h_eff)
    h_eff = np.where(~b1 & use_b2, h_eff_b2, h_eff)
    h_eff = np.where(~b1 & ~use_b2 & below_sfc, 0.0, h_eff)
    h_eff = np.where(np.isfinite(h_eff) & (h_eff >= 0), h_eff, np.nan)
    return h_eff


def project_shadow_coords_vectorized(
    lat: np.ndarray, lon: np.ndarray,
    h:   np.ndarray, h_sfc_grid: np.ndarray,
    sza: np.ndarray, saa: np.ndarray, vza: np.ndarray, vaa: np.ndarray,
    ii:  np.ndarray, jj:  np.ndarray,
    params: ShadowParams,
) -> Tuple[np.ndarray, np.ndarray]:
    """Vectorized DARCLOS projection (Trees et al. 2022, Eqs. 2-7).

    For each source pixel ``(ii[k], jj[k])`` return the projected shadow
    ``(lat, lon)`` on the surface.
    """
    theta0 = np.radians(sza[ii, jj])
    phi0   = np.radians(saa[ii, jj])
    theta  = np.radians(vza[ii, jj])
    phi    = np.radians(vaa[ii, jj])
    h_s    = h[ii, jj]
    h_sfc  = h_sfc_grid[ii, jj]
    c_lat  = lat[ii, jj]
    c_lon  = lon[ii, jj]

    xn  = h_s * np.tan(theta)  * np.sin(phi)
    yn  = h_s * np.tan(theta)  * np.cos(phi)
    xsh = xn - h_s * np.tan(theta0) * np.sin(phi0)
    ysh = yn - h_s * np.tan(theta0) * np.cos(phi0)

    delta_lat = ysh / (params.m_earth + h_sfc)
    delta_lon = xsh / ((params.n_earth + h_sfc) * np.cos(np.radians(c_lat)))
    shadow_lat = c_lat + np.degrees(delta_lat)
    shadow_lon = c_lon + np.degrees(delta_lon)
    return shadow_lat, shadow_lon


def draw_line(r0: int, c0: int, r1: int, c1: int, shape: Tuple[int, int]):
    """Bresenham's line — pixels visited between two grid points (inclusive)."""
    steep = abs(r1 - r0) > abs(c1 - c0)
    if steep:
        r0, c0 = c0, r0
        r1, c1 = c1, r1
    if c0 > c1:
        c0, c1 = c1, c0
        r0, r1 = r1, r0
    dr = abs(r1 - r0)
    dc = c1 - c0
    error = dc / 2
    rstep = 1 if r0 < r1 else -1
    rr, cc = [], []
    r = r0
    for c in range(c0, c1 + 1):
        coord_r = r if not steep else c
        coord_c = c if not steep else r
        if 0 <= coord_r < shape[0] and 0 <= coord_c < shape[1]:
            rr.append(coord_r)
            cc.append(coord_c)
        error -= dr
        if error < 0:
            r += rstep
            error += dc
    return np.array(rr), np.array(cc)


def compute_masks(
    lat: np.ndarray, lon: np.ndarray,
    cloud_fraction: np.ndarray,
    cloud_pressure: np.ndarray, surface_pressure: np.ndarray,
    terrain_height: np.ndarray, cth_l1b: np.ndarray,
    sza: np.ndarray, saa: np.ndarray, vza: np.ndarray, vaa: np.ndarray,
    params: ShadowParams,
):
    """Run the full DARCLOS-TEMPO algorithm on one granule.

    Returns
    -------
    cloud_mask, potential_mask, actual_mask : (M, N) bool arrays in native
        ``(mirror_step, xtrack)`` layout.
    diag : dict
        ``{'n_source', 'n_dropped_height', 'n_dropped_angles'}``.

    Raises
    ------
    ValueError
        If more than ``params.max_drop_frac`` of source pixels are dropped for
        invalid height — granule is likely broken.
    """
    cloud_mask = cloud_fraction >= params.cloud_threshold
    potential_mask = np.zeros_like(cloud_mask, dtype=bool)

    h_grid = compute_heights_vectorized(
        cth_l1b, cloud_pressure, surface_pressure, terrain_height, params,
    )

    ii_all, jj_all = np.where(cloud_mask)
    n_total = len(ii_all)
    diag = {
        "n_source": int(n_total),
        "n_dropped_height": 0,
        "n_dropped_angles": 0,
    }
    if n_total == 0:
        actual_mask = np.zeros_like(cloud_mask, dtype=bool)
        return cloud_mask, potential_mask, actual_mask, diag

    h_valid = np.isfinite(h_grid[ii_all, jj_all])
    diag["n_dropped_height"] = int((~h_valid).sum())
    ii = ii_all[h_valid]
    jj = jj_all[h_valid]

    shadow_lat, shadow_lon = project_shadow_coords_vectorized(
        lat, lon, h_grid, terrain_height, sza, saa, vza, vaa, ii, jj, params,
    )
    proj_ok = np.isfinite(shadow_lat) & np.isfinite(shadow_lon)
    diag["n_dropped_angles"] = int((~proj_ok).sum())
    ii = ii[proj_ok]
    jj = jj[proj_ok]
    shadow_lat = shadow_lat[proj_ok]
    shadow_lon = shadow_lon[proj_ok]

    grid_lat = lat.ravel()
    grid_lon = lon.ravel()
    valid_flat = np.isfinite(grid_lat) & np.isfinite(grid_lon)
    grid_pts = np.column_stack([grid_lat[valid_flat], grid_lon[valid_flat]])
    grid_idx_back = np.flatnonzero(valid_flat)
    tree = cKDTree(grid_pts)
    _, nbr_idx = tree.query(np.column_stack([shadow_lat, shadow_lon]))
    flat_idx = grid_idx_back[nbr_idx]
    shadow_i, shadow_j = np.unravel_index(flat_idx, lat.shape)

    for k in range(len(ii)):
        rr, cc = draw_line(
            int(ii[k]), int(jj[k]),
            int(shadow_i[k]), int(shadow_j[k]),
            lat.shape,
        )
        if rr.size == 0:
            continue
        valid = ~cloud_mask[rr, cc]
        potential_mask[rr[valid], cc[valid]] = True

    actual_mask = (
        (cloud_fraction > -999)
        & (cloud_fraction < params.shadow_threshold)
        & potential_mask
    )

    frac_h = diag["n_dropped_height"] / max(n_total, 1)
    if frac_h > params.max_drop_frac:
        raise ValueError(
            f"{diag['n_dropped_height']}/{n_total} ({frac_h:.1%}) source pixels "
            f"lack a valid cloud height — exceeds max_drop_frac = "
            f"{params.max_drop_frac:.1%}."
        )
    return cloud_mask, potential_mask, actual_mask, diag
