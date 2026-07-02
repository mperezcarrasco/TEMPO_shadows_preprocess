# TEMPO Cloud Shadow Preprocessing — Project Guide

Internal reference for anyone (human or Claude) working on this repository.
Complements the public `README.md`, which is written for external users and
does not reference the docs and notebooks catalogued here.

---

## 1. Motivation

Cloud shadows are a systematic, currently unmitigated error source in TEMPO
UV/VIS trace-gas retrievals. When a cloud casts a shadow on the surface,
the shadowed pixel receives reduced direct solar illumination. Viewed from
the geostationary instrument, this appears as an anomalously dark scene —
not due to cloud optical depth in the line of sight, but because the
surface itself is under-illuminated.

Consequences that motivate the pipeline:

- **ECF underestimation.** TEMPO's CLDO4 cloud algorithm interprets the
  darkened scene reflectance as a low effective cloud fraction. Shadow
  pixels can pass the `ECF < 0.2` quality filter while being
  radiometrically contaminated.
- **AMF bias.** Trace-gas air mass factors are computed assuming
  climatological surface reflectance. A shadowed pixel has a lower actual
  reflectance, biasing the AMF and inflating apparent NO₂, HCHO, SO₂, and
  O₃ columns.
- **Hourly cadence amplifies exposure.** TEMPO's geostationary orbit
  enables hourly scans of North America. Shadow positions shift
  predictably across granules, so a stationary cloud field can contaminate
  the same urban or biogenic pixel repeatedly across scan cycles.

This project adapts **DARCLOS** (Trees et al., 2022, AMT) — a cloud-shadow
detection algorithm originally developed for TROPOMI — to TEMPO. DARCLOS
produces three per-pixel flags:

- `PCSF` — geometric candidate (pixel falls within projected shadow
  triangle).
- `ACSF` — radiometrically confirmed shadow (scene darker than DLER
  climatology by more than 15 %).
- `SCSF` — wavelength-resolved flag at each retrieval window (NO₂, HCHO,
  SO₂).

Our adaptation implements PCSF as in DARCLOS, replaces ACSF with a
single-wavelength surrogate based on the CLDO4 ECF inversion itself, and
omits SCSF pending a full SCNLER computation from L1B radiances. Full
scientific rationale in `docs/DARCLOS-TEMPO.md` and `docs/methodology.md`.

---

## 2. Codebase Structure

```
preprocess_shadows/
├── CLAUDE.md                  ← this file
├── README.md                  ← public, external-facing overview
├── requirements.txt
├── Dockerfile
├── build_container.sh
├── run_container.sh
│
├── scripts/                   ← production pipeline
│   ├── shadows.py             ← DARCLOS algorithm (pure NumPy/SciPy, no I/O)
│   ├── io_utils.py            ← L1B/L2 loaders + GeoTIFF + shapefile writers
│   ├── run_day.py             ← granule-level CLI
│   └── run_scan.py            ← scan-level CLI (primary mode)
│
├── configs/
│   └── day_example.yaml       ← config schema + defaults
│
├── docs/                      ← science + implementation documentation
├── notebooks/                 ← exploratory + reference implementations
├── data/                      ← where you drop input L1B / L2 for local runs
│   ├── raw_l1/                ← TEMPO L1B radiances
│   ├── raw_l2_v3/             ← V03 CLDO4 cloud products
│   └── raw_l2_v4/             ← V04 CLDO4 cloud products
└── results/, results_scan/    ← pipeline outputs (created at runtime)
    └── {yyyy}/{mm}/{dd}/      ← one directory per processed day
```

---

## 3. Development Principles

- **Fail loudly.** Never silently fall back on default values for
  thresholds, cloud-height conversions, or wavelength selections. Missing
  or unexpected inputs must raise explicit errors.
- **Explicit configuration.** All algorithm parameters (ECF thresholds,
  contrast threshold, safety factor, SZA cutoff) must be named constants
  traceable to the DARCLOS paper or the TEMPO ATBD.
- **Separation of concerns.** Geometry (PCSF), radiometry (ACSF), and I/O
  live in separate modules. `shadows.py` has no file I/O; `io_utils.py`
  has no algorithm logic; the two CLIs contain only orchestration.
- **Shape assertions at boundaries.** Assert input array shapes
  (`mirror_step × xtrack`) before and after key operations.
- **Research integrity.** Log the full configuration, data paths, and —
  where relevant — the git hash at the start of every experiment run.

---

## 4. Key Algorithm Parameters

| Parameter | Value | Source |
|---|---|---|
| Safety factor `C` | 0.5 | Trees et al. (2022) Eq. 1 |
| ACSF contrast threshold (original DARCLOS) | −15 % | Trees et al. (2022) |
| Cloud-source ECF threshold | ≥ 0.30 | TEMPO cloud team |
| Shadow ECF threshold (ACSF surrogate) | < 0.05 | Conservative clear-sky proxy |
| Hypsometric scale height | 8500 m | Standard troposphere |
| Cloud altitude cap | 16 000 m | Tropopause guard |
| Max drop fraction | 0.10–0.30 | Tuned per V0x |
| SZA cutoff (recommended, not enforced yet) | < 75° | TEMPO L2 QA convention |
| Cloud Lambertian albedo (in CLDO4) | 0.8 | CLDO4 ATBD |

---

## 5. Known limitations

The limitations a first-time user is most likely to encounter.

**Open-water false positives.** Over open ocean, the GLER is 0.03–0.05,
so the retrieved ECF naturally falls below `shadow_threshold = 0.05`
without any shadow being present. When the PCSF projection crosses open
water, ACSF fires spuriously. This is the principal precision risk of
the current algorithm.

**Snow and bright-surface false negatives.** Over surfaces with GLER
above ~0.5, even a real shadow does not depress ECF below 0.05, so no
ACSF is raised. Shadow detection over bright surfaces remains an open
problem.

**Height bias for deep convection.** OCP is a radiative centroid, not
a geometric top. Deep convective clouds have geometric tops several km
above OCP, so the projection underestimates shadow length for them. The
safety factor `C = 0.5` absorbs part of this bias but not all.

**Single-wavelength check.** The ACSF surrogate operates at 466 nm only.
It cannot distinguish aerosol darkening from shadow darkening (both look
similar at one wavelength; DARCLOS's SCSF check distinguishes them by
inspecting the spectral slope).

**Line vs polygon umbra.** The Bresenham line captures shadow *length*
but understates *width*. Real umbras are 1–2 TEMPO pixels wide
cross-track.

**No SZA cutoff yet.** The algorithm runs at any SZA. Above ~80° the
projection becomes geometrically unstable.

**Bounding-box GeoTIFF georeferencing.** TEMPO's swath is curvilinear in
lat/lon. The `from_bounds` affine assumes a regular lat/lon grid and
introduces 1–2-pixel geometric distortion at scan edges. Use the
shapefiles (not the GeoTIFF) when pixel-accurate coordinates matter.

**No quantitative validation.** Visual inspection against RGB is
plausible but not sufficient. GOES-East ABI validation is the natural
next step; a collocation pipeline is not yet implemented.

Which of these can be addressed by tuning versus by a code change:

| Limitation | Fix by config? |
|---|---|
| Open-water false positives | Partial (raise `shadow_threshold` on ocean-heavy days); full fix requires code |
| Snow false negatives | No (needs a bright-surface-aware algorithm) |
| Deep-convection height bias | Partial (raise `safety_factor_c`); full fix requires cloud-optical-thickness input |
| Bounding-box GeoTIFF | Partial (use shapefiles); full fix requires GCP-based warping |

Full analysis (including the roadmap to close each item) is in
`docs/methodology.md` § 5 and in the paper draft `docs/paper/paper.tex`
§ 5.

---

## 6. Notebooks

The `notebooks/` directory is the historical record of how the current
algorithm converged. Not part of the production path; useful when
debugging a regression or extending the method.

| Notebook | Purpose | Status |
|---|---|---|
| `Cloud_Shadows_v3_vectorized.ipynb` | Reference for the algorithm now shipped in `scripts/shadows.py`. Vectorized projection, ECEF k-d tree, Bresenham line, ECF-based ACSF. | **Canonical** |
| `Cloud_Shadows_v2_height.ipynb` | Step-by-step application of the cloud-height fix on top of the Debug baseline. Demonstrates why the L1B branch alone is not enough (fill-valued CTH). | Historical |
| `Cloud Shadows Masking-Debug.ipynb` | Original per-pixel implementation. Slow; documents the silent-NaN bug in the azimuth handling that was later fixed by reading angles from L1B. | Historical |
| `DARCLOS_TEMPO_implementation.ipynb` | Full-DARCLOS prototype: polygon PCSF, Rayleigh-corrected SCNLER, 13-wavelength contrast. Produces sparser outputs than the v3 line-based method; the reason we abandoned polygons for the current release. Kept as the starting point for future SCSF work. | Prototype |
| `Preprocess Tempo Clouds Shadows RGB.ipynb` | Constructs the `.npy` RGB + mask dataset used by the sibling segmentation repository. Applies the older algorithm; superseded by the scripts pipeline for label generation. | Superseded |
| `Preprocess GLER446 SZA VZA RAA.ipynb` | Exploratory script for surface-reflectance and geometry channels. Reference for the SCSF future-work item. | Exploratory |
| `Preprocess Tempo Clouds RGB.ipynb` | RGB-only preprocessing (no shadow masking). Predates the shadow work. | Historical |
| `Merge_Scans.ipynb` | Post-hoc mosaic of per-granule outputs into per-scan products, via `rasterio.merge`. Superseded by `scripts/run_scan.py` for production, kept as a diagnostic tool to demonstrate the seam artefacts that scan-level processing avoids. | Diagnostic |

When adding or modifying a notebook, note it here. Notebook filenames
with spaces are legacy and should not be introduced for new notebooks.

---

## 7. Docs

The `docs/` directory has the science context and the technical reports
that back the code. Everything in the paper draft is grounded in one of
these.

| File | Purpose |
|---|---|
| `DARCLOS-TEMPO.md` | Full science rationale for the TROPOMI → TEMPO adaptation. The design document written before the pipeline was implemented; still the reference for *why* each adaptation was chosen. |
| `methodology.md` | End-to-end technical report on the method as implemented. Written after the pipeline stabilized. Includes explicit limitations analysis and roadmap. |
| `TEMPO_pipeline.md` | TEMPO L0 → L1B → L2 → L3 processing chain overview. Reference for anyone new to the mission's data products. |
| `data_structure.md` | Inventory of the L1B and L2 variables used by the algorithm, with fill-value conventions and dimensional layout notes. |
| `paper_draft.md` | Paper draft in Markdown. Follows the AMT structure. |
| `paper/` | Same draft in LaTeX: `paper.tex`, `references.bib`, `Makefile`, `README.md`, and a `figures/` directory for final figures. |
| `amt-15-3121-2022.pdf` | Trees et al. (2022) — the DARCLOS paper this work adapts. |
| `Earth and Space Science - 2025 - Wang - Algorithm Theoretical Basis for Version 3 TEMPO O2‐O2 Cloud Product.pdf` | Wang et al. (2025) — the CLDO4 V3 ATBD. Section 3.2 gives the MLER equation and the ECF inversion we exploit for the ACSF surrogate. |

Precedence when the three long-form docs disagree:
`docs/methodology.md` > `docs/paper_draft.md` > `docs/DARCLOS-TEMPO.md`.
The design doc predates the implementation and reflects the polygon
projection we abandoned; when it conflicts with the methodology report,
trust the methodology report.

---

## 8. Design decisions and their history

Anyone touching the algorithm should know why the current choices were
made. The short version:

1. **Bresenham line, not the DARCLOS umbra polygon.** The full polygon
   projection was implemented first
   (`DARCLOS_TEMPO_implementation.ipynb`) and produced sparser, more
   fragmented ACSF masks because single-cloud-pixel polygons combined
   with the strict `ECF < 0.05` filter dropped too many candidate pixels.
   The line captures shadow length correctly and, ANDed with the
   radiometric filter, gives visually plausible outputs. A future
   polygon-with-cluster-union implementation is the natural next step,
   but do not swap it in without validating against the current line
   output on the September 2025 corpus.

2. **CLDO4 ECF as a single-wavelength ACSF surrogate, not full SCNLER.**
   The CLDO4 MLER inversion at 466 nm (Wang et al. 2025, § 3.2) already
   compares the measured radiance against GLER. A shadowed clear pixel
   drives ECF toward zero. `ECF < 0.05` is therefore the same signal
   that DARCLOS's `Γ(λ_max) < −15 %` criterion extracts, without
   requiring the Rayleigh-correction LUT or the DLER climatology.

3. **Angles from L1B, not L2.** In V03 and V04, L2
   `viewing_azimuth_angle` is entirely fill-valued and
   `solar_azimuth_angle` is ~94 % fill-valued. The Debug notebook used
   the L2 values silently; NaN propagation landed the `argmin` on grid
   index (0, 0) and drew a spurious Bresenham line from every cloud
   pixel toward the corner. This looked plausible in RGB overlay because
   the spurious lines crossed enough genuinely dark pixels for the
   radiometric AND to latch on. The L1B `band_290_490_nm` group is fully
   populated and is the authoritative source.

4. **`h5py` for both L1B and L2, not `netCDF4.Dataset`.** On shared NFS
   storage, `netCDF4` raises `[Errno -101] NetCDF: HDF error` on files
   that `h5py` opens fine. Root cause is HDF5 file-locking; the
   workaround is `HDF5_USE_FILE_LOCKING=FALSE`, but we bypass the issue
   entirely by using `h5py` directly. Fill values are handled per
   variable via a small `_h5_read_*` helper family.

5. **`fiona` directly for shapefiles, not `GeoDataFrame.to_file`.**
   GeoPandas' `to_file` calls `np.array(geom, copy=False)` on the
   geometry column, which is a hard error under NumPy 2.0. Writing
   per-feature through `fiona` sidesteps the incompatibility.
   `geopandas` is still imported elsewhere but never on the write path.

6. **`run_scan.py` merges L1B/L2 arrays before running the algorithm,
   not after.** Post-hoc mosaicking of per-granule outputs (see
   `Merge_Scans.ipynb`) produces seam artefacts because each granule has
   its own bounding-box affine. More importantly, shadows that cross
   granule boundaries are undetectable at the per-granule level. Merging
   the mirror-step arrays before the algorithm runs solves both.

7. **Constant scale height, not a MERRA-2 profile, for OCP → height.**
   The DARCLOS safety factor `C = 0.5` absorbs the ~10 % error
   introduced by the constant. A MERRA-2 pipeline component would refine
   height at high latitudes / in winter, but is not required for
   first-order shadow detection.

---

## 9. Common failure modes and how to diagnose them

Both `run_day.py` and `run_scan.py` isolate failures at the granule (or
scan) level: one broken input does not sink the rest of the run. The
intended contract is:

- **No L2 match for an L1B granule** → logged warning, granule skipped.
- **Any of the four L1B angles entirely fill-valued** → raises
  `ValueError` for that granule; other granules still process.
- **More than `max_drop_frac` of source pixels have non-physical cloud
  height** → raises `ValueError` for that granule / scan; other units
  still process.
- **End of run** → summary line reports `processed / no_l2 / failed`
  counts, so partial failure is visible at a glance.

Symptom-driven diagnosis:

| Symptom | Likely cause | Where to look |
|---|---|---|
| `[Errno -101] NetCDF: HDF error` | Shared-storage file-locking. | Set `HDF5_USE_FILE_LOCKING=FALSE` or verify `h5py` is actually used. |
| `ValueError: N/M (X %) source pixels lack a valid cloud height` | V04 OCP retrieval skipped on many pixels (snow, high SZA). | Raise `max_drop_frac` in the config, or add explicit quality masking (SZA / snow_ice / PQF). |
| All ACSF polygons empty | L1B azimuth fields fill-valued for this granule; algorithm dropped every source pixel via `n_dropped_angles`. | Grep run log for `[angles] dropped`. If 100 %, this granule cannot be processed. |
| ACSF polygons over open ocean | Known false-positive mode (§ 5 above). | Add a brightness gate `GLER466 > 0.05` before firing ACSF; not yet implemented. |
| Merged-scan seam artefacts in `Merge_Scans.ipynb` output | Per-granule GeoTIFFs have per-granule bounding-box affines. | Switch to `scripts/run_scan.py` instead. |
| Shapefile write fails with NumPy 2 error | Code path went through `GeoDataFrame.to_file`. | Route through the `fiona`-direct writer in `io_utils.py`. |
| Cross-boundary shadows not detected | Running `run_day.py` instead of `run_scan.py`. | Use `run_scan.py`. |

---

## 10. References

Papers:

- Trees, V. J. H., Wang, P., & Stammes, P. (2022). *DARCLOS: a cloud
  shadow detection algorithm for TROPOMI.* AMT 15, 3121–3140.
  doi:10.5194/amt-15-3121-2022. Local copy at
  `docs/amt-15-3121-2022.pdf`.
- Wang, H., Nowlan, C. R., González Abad, G., et al. (2025). *Algorithm
  Theoretical Basis for Version 3 TEMPO O₂–O₂ Cloud Product.* ESS 12,
  e2024EA004165. doi:10.1029/2024EA004165. Local copy at
  `docs/Earth and Space Science - 2025 - Wang - Algorithm Theoretical Basis for Version 3 TEMPO O2‐O2 Cloud Product.pdf`.
- Vasilkov, A., et al. (2018). *Cloud optical centroid pressure from
  the OMI 477 nm O₂–O₂ band: an updated algorithm.* AMT 11, 4093–4107.
- Zoogman, P., et al. (2017). *Tropospheric Emissions: Monitoring of
  Pollution (TEMPO).* JQSRT 186, 17–39.
- Nowlan, C. R., et al. (2025). *TEMPO NO₂ ATBD.* SAO SDPC.

Additional bibliography for the manuscript is in
`docs/paper/references.bib`.
