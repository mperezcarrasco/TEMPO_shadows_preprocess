# DARCLOS-TEMPO — cloud and cloud-shadow detection for the TEMPO instrument

Python implementation of an adaptation of the DARCLOS cloud-shadow
detection algorithm (Trees, Wang & Stammes, 2022, *Atmospheric
Measurement Techniques*) to the geostationary UV-VIS spectrometer
TEMPO. Reads TEMPO L1B radiance and CLDO4 L2 cloud products, produces
per-pixel cloud, potential-shadow, and actual-shadow masks, and writes
them as georeferenced GeoTIFF + shapefile outputs.

Written for team use ahead of a methods paper. Intended for
reproduction of the results we obtained on 17–18 September 2025, and
for your own runs on other TEMPO days.

> **Status: work in progress.** The method is under active validation and has not yet been checked quantitatively against an independent ground truth (in development). Algorithm parameters or thresholds may change as validation progresses. Known failure modes documented so far include false positives over open ocean, false negatives over snow and other bright surfaces, and shadow-length underestimation.

---

## Table of contents

1. Objectives
2. Repository layout
3. Installation
4. Quick start
5. How the algorithm works
6. Processing modes: scan-level and granule-level
7. Workflow: from raw data to shapefiles
8. Configuration parameters
9. Outputs
10. Contributing / house rules
11. References
12. Citation

---

## 1. Objectives

Cloud shadows are a systematic error source in the TEMPO trace-gas
retrievals. A pixel under the shadow of a nearby cloud is darker than
its clear-sky climatology predicts. The CLDO4 cloud algorithm attributes
part of that darkening to a lower effective cloud fraction, which lets
the pixel pass the standard `ECF < 0.2` NO₂ quality filter while still
being radiometrically biased. The bias then propagates into the
air-mass-factor calculation and into the retrieved NO₂, HCHO, SO₂ and
O₃ columns.

There is no operational cloud-shadow product for TEMPO. This
repository fills that gap:

- **Detect** the cloud shadows in each TEMPO scan or granule.
- **Georeference** the results so they can be used in downstream QA
filters and in machine-learning training data.
- **Do this at scale**: the pipeline processes a full day (14–15 scans,
~250 granules) in a few minutes on one core.

---

## 2. Repository layout

```
preprocess_shadows/
├── README.md                    ← this file
├── requirements.txt
├── Dockerfile                   ← reproducible container build
├── build_container.sh
├── run_container.sh
│
├── scripts/                     ← the pipeline (CLI-driven)
│   ├── shadows.py               ← DARCLOS algorithm (pure NumPy/SciPy)
│   ├── io_utils.py              ← L1B/L2 loaders + GeoTIFF/shapefile writers
│   ├── run_day.py               ← granule-level CLI
│   └── run_scan.py              ← scan-level CLI (recommended)
│
├── configs/
│   └── day_example.yaml         ← example YAML config
│
├── data/                        ← where you drop input L1B / L2 for local runs
│   ├── raw_l1/                  ← TEMPO L1B radiances
│   ├── raw_l2_v3/               ← V03 CLDO4 cloud products
│   └── raw_l2_v4/               ← V04 CLDO4 cloud products
│
└── results/, results_scan/      ← pipeline outputs (created at runtime)
    └── {yyyy}/{mm}/{dd}/        ← one directory per processed day
```

`data/`, `results/`, and `results_scan/` are not source-controlled. The
`data/` layout shown above is the convention when the archive lives
next to the code; more commonly `base_path` in the config points at a
mounted archive elsewhere on the machine (see § 8.1). `results/` and
`results_scan/` are created by the pipeline on first run.

---

## 3. Installation

The pipeline is Python 3.10+ with NumPy, SciPy, h5py, rasterio, fiona,
GeoPandas, Shapely, and PyYAML. Two supported installation paths:

### Option A — local virtual environment

```bash
git clone <repository-url> preprocess_shadows
cd preprocess_shadows
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Option B — Docker

```bash
bash build_container.sh
bash run_container.sh
```

The Docker image includes GDAL and PROJ pinned to versions known to
work with the current `rasterio` / `fiona` releases. Use it if you hit
GDAL/HDF5 version conflicts on your host.

### If you run on shared NFS storage

Some clusters need HDF5 file-locking disabled for `h5py` to open TEMPO
files:

```bash
export HDF5_USE_FILE_LOCKING=FALSE
```

Add this to your `~/.bashrc` or your Slurm job wrapper.

---

## 4. Quick start

Process one TEMPO scan-day and produce per-scan outputs (recommended
mode):

```bash
# 1. Copy the example config and edit the date + paths.
cp configs/day_example.yaml configs/2025-09-17.yaml
$EDITOR configs/2025-09-17.yaml

# 2. Run.
python scripts/run_scan.py --config configs/2025-09-17.yaml \
    --log-file logs/2025-09-17.log
```

This writes, per scan, one GeoTIFF and three shapefiles into
`{output_root}_scan/2025/09/17/`.

For a granule-by-granule run instead:

```bash
python scripts/run_day.py --config configs/2025-09-17.yaml
```

which writes per-granule outputs into `{output_root}/2025/09/17/`.

---

## 5. How the algorithm works

The method has two stages, matching the DARCLOS architecture:

1. **Geometric shadow projection (PCSF, Potential Cloud Shadow Flag).**
  For every cloud-source pixel (defined as `ECF ≥ 0.30`), compute
   where its shadow lands on the ground given the cloud's height and
   the sun's position, then flag every pixel between the cloud and its
   projected shadow tip.
2. **Radiometric confirmation (ACSF, Actual Cloud Shadow Flag).**
  Among the PCSF-flagged pixels, keep only those whose retrieved ECF
   is below a shadow threshold (`ECF < 0.05` by default). Physically
   this filters pixels whose CLDO4 retrieval interpreted the surface as
   darker than the GLER climatology — the same signal DARCLOS extracts
   from its SceneLER-vs-DLER contrast, exposed here for free by the
   CLDO4 MLER inversion at 466 nm.

The geometric stage uses:

- **Height from OCP.** TEMPO reports Optical Centroid Pressure, not
cloud-top height. Height is derived from a hypsometric formula
`h = H_scale · ln(p_sfc / p_cloud) + terrain`, with `H_scale = 8500 m`
and altitude capped at 16 km. The DARCLOS safety factor `C = 0.5` is
applied to the above-terrain height before projection.
- **Angles from L1B, not L2.** In V03 and V04 the L2 azimuth fields are
mostly fill-valued, so all four angles (solar zenith/azimuth, viewing
zenith/azimuth) are read from the L1B `band_290_490_nm` group where
they are fully populated.
- **Vectorized projection.** DARCLOS Eqs. 2–7 are evaluated on the
full source-pixel array in one NumPy call.
- **ECEF k-d-tree for nearest-pixel lookup.** Projected shadow
(lat, lon) points are matched to the granule/scan pixel grid via a
single batched `scipy.spatial.cKDTree.query` in Earth-Centred
Earth-Fixed coordinates. This avoids the `cos(lat)` bias of a naive
Euclidean metric in degrees, and it turns a per-pixel `argmin` over
the whole grid into an `O(N log M)` batched lookup.
- **Bresenham line rasterization.** The umbra footprint is approximated
by a Bresenham line from the source pixel to the projected shadow
tip. Limitations of this choice (line vs polygon) are discussed in
§ 10.

---

## 6. Processing modes: scan-level and granule-level

The pipeline exposes two CLI drivers, both reading the same YAML
config.

### 6.1 Scan-level (`run_scan.py`) — **the recommended mode**

TEMPO acquires each hourly scan as a sequence of 9–11 granules taken
in ~6.7-minute slices. `run_scan.py`:

1. Discovers all L1B/L2 pairs for the configured date.
2. Groups them by scan number (the `S<scan>` token in the filename).
3. Concatenates each scan's L1B and L2 arrays along the `mirror_step`
  axis **before** running the DARCLOS algorithm.
4. Runs the algorithm once per scan on the merged grid.
5. Writes one GeoTIFF and three shapefiles per scan.

Why merge before running:

- **Shadows that cross granule boundaries are detected.** A cloud near
the eastern edge of granule *n* can project a shadow onto candidate
pixels in granule *n+1*. Granule-level processing cannot see that;
scan-level processing does.
- **Whole-scan validity guard.** The height-validity threshold
(`max_drop_frac`) is evaluated over the full scan. A single bad
granule with many failed OCP retrievals no longer fails the scan.
- **Coherent georeferencing.** One bounding-box affine covers the
whole scan, so there are no seam artefacts of the kind seen when
mosaicking per-granule GeoTIFFs after the fact.

Trade-off: the bounding-box affine spans a larger area, so
swath-grid distortion at scan edges is slightly larger than for one
granule. For GIS overlay this is invisible; for pixel-accurate
georeferencing you should reproject via GCPs — see § 10.

### 6.2 Granule-level (`run_day.py`)

`run_day.py` processes each granule independently. It is useful for:

- Quick QA of a single granule — smaller inputs, faster feedback.
- Debugging: the per-granule diagnostics point to exactly which
granule caused a problem.
- Compatibility with existing per-granule downstream pipelines that
expect one file set per L1B granule.

Use it as the default only if your downstream expects per-granule
outputs. For everything else, use `run_scan.py`.

---

## 7. Workflow: from raw data to shapefiles

The end-to-end flow, from remote TEMPO archive to labelled shapefiles:

```
┌──────────────────────────────────────────────────────────────┐
│  Raw TEMPO archive                                            │
│    {base_path}/TEMPO_RAD_L1_V04/{yyyy}/{mm}/{dd}/*.nc          │
│    {base_path}/TEMPO_CLDO4_L2_V04/{yyyy}/{mm}/{dd}/*.nc        │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Config file (YAML)                                           │
│    configs/2025-09-17.yaml                                    │
│    ── date, paths, algorithm parameters, output roots        │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  scripts/run_scan.py --config configs/2025-09-17.yaml         │
│    1. Discover L1B files for the day                          │
│    2. Group by scan number                                    │
│    3. For each scan:                                          │
│         a. Pair with L2 files                                 │
│         b. Load and concatenate L1B + L2 along mirror_step    │
│         c. Compute cloud height (OCP → hypsometric)          │
│         d. Project shadows (vectorized DARCLOS Eqs. 2–7)     │
│         e. cKDTree nearest-pixel lookup                       │
│         f. Bresenham line rasterization → PCSF                │
│         g. ACSF = PCSF ∧ (ECF < shadow_threshold)             │
│         h. Write GeoTIFF + 3 shapefiles                       │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  {output_root}_scan/2025/09/17/                               │
│    rgb_S<scan>.tif                                            │
│    S<scan>_clouds.shp                                         │
│    S<scan>_potential_shadows.shp                              │
│    S<scan>_actual_shadows.shp                                 │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Downstream consumers                                         │
│    ── Visual inspection in QGIS                               │
│    ── ML training data (segmentation repository)              │
│    ── Trace-gas retrieval quality filters                     │
└──────────────────────────────────────────────────────────────┘
```

### 7.1 Scale-out across many days

Each invocation processes one day. Backfilling a range of days:

```bash
for d in $(seq 1 30); do
    day=$(printf "%02d" $d)
    sed "s/^day: .*/day: ${day}/" configs/day_example.yaml \
        > /tmp/cfg_${day}.yaml
    python scripts/run_scan.py --config /tmp/cfg_${day}.yaml \
        --log-file logs/2025-09-${day}.log
done
```

On a compute cluster, submit each day as a separate Slurm job or
job-array element. The pipeline does not spawn workers internally; that
choice makes logging, failure isolation, and resume trivial.

### 7.2 Visual QA after each run

Load the output GeoTIFF and shapefiles into QGIS (they share an
EPSG:4326 CRS). Check three things per scan:

1. **Direction.** ACSF polygons extend away from the casting cloud on
  the side opposite the sun.
2. **Extent.** Shadow polygons look plausibly long given the cloud
  height and the SZA.
3. **Pairing.** Every visible cloud band in the RGB has an associated
  ACSF polygon on its sun-opposite side.

Granules that fail these checks systematically (e.g. over open ocean,
where ACSF false-positives are known) should be excluded from
downstream use.

---

## 8. Configuration parameters

The full parameter list is in `configs/day_example.yaml`. The three
groups:

### 8.1 Date and paths


| Key                                  | Purpose                                                                            |
| ------------------------------------ | ---------------------------------------------------------------------------------- |
| `year`, `month`, `day`               | Date to process. Leading zeros are added automatically.                            |
| `base_path`                          | Root of the TEMPO archive (contains `TEMPO_RAD_L1_V04/…`).                         |
| `version`                            | CLDO4 version, `V04` (recommended) or `V03`.                                       |
| `l1_dir_template`, `l2_dir_template` | Path templates using `{base_path}/{version}/{year}/{month}/{day}` placeholders.    |
| `l1_band`                            | L1B band group holding the angles + `cloud_top_height`. Default `band_290_490_nm`. |
| `output_root`                        | Where per-granule outputs go. `run_scan.py` writes to `{output_root}_scan`.        |


### 8.2 DARCLOS-TEMPO algorithm parameters


| Key                  | Symbol   | Default     | Source                          |
| -------------------- | -------- | ----------- | ------------------------------- |
| `cloud_threshold`    | τ_cloud  | 0.30        | TEMPO cloud team recommendation |
| `shadow_threshold`   | τ_shadow | 0.05        | DARCLOS-TEMPO, V04-tuned        |
| `safety_factor_c`    | C        | 0.5         | Trees et al. (2022) Eq. 1       |
| `h_scale_m`          | H_scale  | 8500 m      | Standard troposphere            |
| `h_cap_m`            | h_cap    | 16 000 m    | Tropopause guard                |
| `max_drop_frac`      | f_drop   | 0.10–0.30   | Tuned per data quality          |
| `m_earth`, `n_earth` | —        | 6 378 137 m | WGS-84 equatorial radius        |


Each parameter is a named constant traceable to a paper or an ATBD.
The pipeline never silently substitutes a default for a missing config
key: `run_day.py` and `run_scan.py` raise `ValueError` with the exact
list of missing keys.

### 8.3 GeoTIFF appearance


| Key           | Purpose                                                         |
| ------------- | --------------------------------------------------------------- |
| `apply_gamma` | Apply `x^gamma` to the RGB channels before writing the GeoTIFF. |
| `gamma`       | Exponent (default 0.4).                                         |


---

## 9. Outputs

### 9.1 Per scan (`run_scan.py`, `{output_root}_scan/{yyyy}/{mm}/{dd}/`)

```
rgb_S<scan>.tif                       ← 3-band uint8 RGB GeoTIFF (EPSG:4326)
S<scan>_clouds.shp                    ← cloud polygons (ECF ≥ 0.30)
S<scan>_potential_shadows.shp         ← PCSF polygons
S<scan>_actual_shadows.shp            ← ACSF polygons (PCSF ∩ ECF < 0.05)
```

### 9.2 Per granule (`run_day.py`, `{output_root}/{yyyy}/{mm}/{dd}/`)

```
rgb_<L1_basename>.tif
<L1_basename>_clouds.shp
<L1_basename>_potential_shadows.shp
<L1_basename>_actual_shadows.shp
```

### 9.3 Shapefile attributes

All shapefiles are EPSG:4326. Every polygon has:


| Field       | Type  | Contents                                        |
| ----------- | ----- | ----------------------------------------------- |
| `type`      | str   | `cloud`, `potential_shadow`, or `actual_shadow` |
| `name`      | str   | Human-readable label                            |
| `value`     | int   | Mask value (1)                                  |
| `source`    | str   | Originating granule or scan identifier          |
| `area_deg2` | float | Polygon area in square degrees                  |


The three shapefiles are nested by construction:
`actual_shadows ⊆ potential_shadows`; `clouds` is disjoint from both.

### 9.4 Overwrite policy

Both drivers overwrite existing outputs unconditionally. This makes
algorithm changes easy to validate. For large backfills, wrap the
driver in a script that skips already-processed days.

---

## 10. Contributing / house rules

- **Fail loudly.** No silent fallbacks for missing thresholds, missing
paths, or non-finite inputs. If something is wrong, raise.
- **Explicit configuration.** Every algorithm constant lives in the
YAML config or in a named module-level constant. No magic numbers
inline in loops.
- **Separation of concerns.** Geometry (PCSF), radiometry (ACSF),
and I/O live in separate modules. The algorithm in `shadows.py`
has no I/O and can be unit-tested in isolation.
- **Shape assertions at boundaries.** Assert input array shapes
(`mirror_step × xtrack`) before and after key operations.
- **Reproducibility.** Every experiment logs its full config, the
data paths, and — where relevant — the git hash at run start.

Please open an issue before starting a substantial change (adding a
new mask, changing the ACSF definition, replacing the height
formula). Ad-hoc changes without a discussion tend to regress the
visual QA before they improve it.

---

## 11. References

- Trees, V. J. H., Wang, P., & Stammes, P. (2022). *DARCLOS: a cloud
shadow detection algorithm for TROPOMI.* **Atmospheric Measurement
Techniques** 15, 3121–3140. [doi:10.5194/amt-15-3121-2022](https://doi.org/10.5194/amt-15-3121-2022)
- Wang, H., Nowlan, C. R., González Abad, G., et al. (2025).
*Algorithm Theoretical Basis for Version 3 TEMPO O₂–O₂ Cloud
Product.* **Earth and Space Science** 12, e2024EA004165.
[doi:10.1029/2024EA004165](https://doi.org/10.1029/2024EA004165)
- Vasilkov, A., Qin, W., Krotkov, N., et al. (2018). *Cloud optical
centroid pressure from the OMI 477 nm O₂–O₂ band: an updated
algorithm.* **AMT** 11, 4093–4107.
- Zoogman, P., Liu, X., Suleiman, R., et al. (2017). *Tropospheric
Emissions: Monitoring of Pollution (TEMPO).* **JQSRT** 186, 17–39.

---

## 12. Citation

If you use this pipeline in a publication, cite the DARCLOS paper and
the current DARCLOS-TEMPO draft:

```bibtex
@article{trees2022darclos,
  author  = {Trees, V. J. H. and Wang, P. and Stammes, P.},
  title   = {{DARCLOS}: a cloud shadow detection algorithm for {TROPOMI}},
  journal = {Atmospheric Measurement Techniques},
  volume  = {15},
  pages   = {3121--3140},
  year    = {2022},
  doi     = {10.5194/amt-15-3121-2022}
}

@misc{darclos-tempo,
  author = {P{\'e}rez-Carrasco, M. and Zhu, Q. and others},
  title  = {{DARCLOS-TEMPO}: A cloud shadow detection algorithm
            adapted from {TROPOMI} to the geostationary {TEMPO}
            instrument},
  note   = {Manuscript in preparation},
  year   = {2026}
}
```

---

## Contact

For scientific questions about the adaptation, open a GitHub issue in
this repository or email
[ma.ignacioperezc@gmail.com](mailto:ma.ignacioperezc@gmail.com).
For issues that involve TEMPO L1B/L2 products themselves, contact the
TEMPO SDPC through the ASDC.