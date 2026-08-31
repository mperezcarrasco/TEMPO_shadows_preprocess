# Cloud Shadow Detection for TEMPO — Methodology Report

This document describes the pipeline implemented in `preprocess_shadows/scripts/`
for producing per-pixel cloud and cloud-shadow masks from TEMPO observations.
It explains the intuition behind the method, what each component is adapted
from, what assumptions we make when we depart from the source papers, and
where the algorithm should be expected to fail.

The intended reader has a basic familiarity with satellite remote sensing but
not necessarily with the DARCLOS paper or the TEMPO CLDO4 algorithm.

---

## 1. The problem in one minute

A cloud above the surface blocks direct sunlight from reaching the ground
beneath and beside it. From a satellite's perspective, the **cloud itself**
appears as a bright pixel (it reflects much of the sunlight back toward space),
while the **shadow** appears as an anomalously dark pixel — not because the
atmosphere there is opaque, but because the ground there is being illuminated
by less direct sunlight.

For TEMPO specifically:

- **Cloud pixels** are flagged by the operational L2 cloud product (CLDO4).
- **Shadow pixels** are *not* part of any operational TEMPO product. They
  must be detected separately.

Detecting shadows matters because TEMPO's trace-gas retrievals (NO₂, HCHO,
SO₂, O₃) interpret a darkened pixel as having a lower-than-expected surface
reflectance. Through the air-mass-factor calculation, that translates into
biased trace-gas columns over exactly the kinds of scenes — urban centres
under afternoon cumulus, biogenic forests in summer — where accurate columns
matter most. The DARCLOS-TEMPO design discussion in
[`DARCLOS-TEMPO.md`](DARCLOS-TEMPO.md) covers the science motivation in depth;
this document focuses on the *method we actually built*.

---

## 2. Intuition

The geometry of a cloud shadow is, in principle, just trigonometry:

```
                 ☀ (sun)
                /
               /  ← SZA (solar zenith angle)
              /
             /
   cloud ───●───────────────── cloud height h
            │\
            │ \    ← shadow direction
            │  \
            │   \
   surface ─┴────●──── shadow tip
                  ↑
                  horizontal offset = h · tan(SZA)
```

If we know:

1. **Where the cloud is** (lat/lon, cloud-top height),
2. **Where the sun is** (solar zenith and azimuth at the moment of
   observation),

then we can compute where on the ground the shadow falls. That is the
*geometric* part of the problem.

The catch is that we never know any of these inputs perfectly. The cloud's
"height" is a retrieval, not a measurement. The cloud might cover only part
of the satellite pixel, so its true centre is uncertain. And — most
importantly — predicting a shadow's *geometric* position does not prove a
shadow is *actually* there: aerosol plumes, dark surfaces, and topography all
darken pixels for other reasons.

So a credible shadow-detection algorithm has two stages:

- **Geometric stage (PCSF — Potential Cloud Shadow Flag).** Project every
  cloud's shadow onto the surface and flag pixels that *could* be in shadow.
- **Radiometric stage (ACSF — Actual Cloud Shadow Flag).** For every PCSF
  pixel, check that the surface is actually darker than would be expected
  from a clear-sky observation of the same place. Keep only the pixels that
  pass both stages.

This two-stage design is the core of DARCLOS (Trees, Wang & Stammes, 2022)
and is what our pipeline implements with a TEMPO-specific simplification of
the radiometric step.

---

## 3. What DARCLOS does (original method)

DARCLOS was designed for TROPOMI, a low-Earth-orbit instrument. It produces
three flags per pixel:

- **PCSF.** Pure geometry. The cloud's four pixel corners are projected
  forward along the sun direction; any clear pixel whose centre falls inside
  the resulting quadrilateral is "potentially shadowed".
- **ACSF.** Radiometric refinement. For each PCSF pixel, DARCLOS computes
  a "scene Lambertian-equivalent reflectance" (SCNLER) from the TOA radiance
  and compares it to a *Directional Lambertian-Equivalent Reflectance*
  (DLER) climatology — a long-term, geometry-aware estimate of what each
  square of ground *should* reflect when not in shadow. If

  ```
  Γ(λ_max) = (SCNLER(λ_max) − DLER(λ_max)) / DLER(λ_max) × 100%   <   −15%
  ```

  at the wavelength λ_max where DLER peaks, the pixel is confirmed as a
  shadow. The −15 % threshold and the choice of λ_max are tuned empirically
  in Trees et al. (2022).
- **SCSF.** The same contrast test repeated at 13 individual wavelengths
  (328–494 nm), giving a per-retrieval-window shadow flag for downstream
  trace-gas algorithms.

DARCLOS-vs-VIIRS validation gives F₁ scores of 0.84–0.95 (Trees et al. 2022).

---

## 4. Adapting DARCLOS to TEMPO

TEMPO differs from TROPOMI in three ways that matter for shadow detection:

1. **Cloud height.** TEMPO's L2 cloud product (CLDO4) reports *Optical
   Centroid Pressure* (OCP, in hPa) — not a physical height.
2. **Surface reflectance.** TEMPO provides GLER, a geometry-dependent
   surface reflectance at 440 and 466 nm only, not the multi-wavelength DLER
   climatology DARCLOS uses.
3. **Geometry.** TEMPO is geostationary, so the *viewing* angles are fixed
   per pixel for life; only the *solar* angles vary across the day.

These three differences drove all of our design decisions. The next four
sections walk through what we chose, and why.

### 4.1 Cloud height: hypsometric conversion of OCP

**Source:** TROPOMI/DARCLOS uses FRESCO physical cloud-top height directly.

**Our choice:** We convert OCP to a height with the hypsometric formula,
using surface pressure from the CLDO4 `support_data` group:

```
h_above_terrain = H_SCALE · ln(p_sfc / p_cloud)
h_cloud_ASL     = h_above_terrain + h_terrain   (clipped to ≤ H_CAP)
h_effective     = (1 + C) · (h_cloud_ASL − h_terrain)
```

with the DARCLOS safety factor `C = 0.5`, a scale height of `H_SCALE = 8500 m`
and an altitude cap of `H_CAP = 16000 m`.

**Why this works.** In the troposphere the constant-scale-height
approximation is correct to ~10 %. Trees et al. (2022) themselves note
that height accuracy of ~100–200 m is enough because the safety factor C
explicitly widens the shadow footprint to absorb residual error.

**Where the L1B `cloud_top_height` is used.** When the L1B band group
provides a finite, physical `cloud_top_height` (GOES-East-ABI-derived,
co-registered to TEMPO), we use it in preference to the OCP-derived value.
In the V03/V04 data available so far this field is mostly fill-valued, so
the hypsometric fallback runs for almost every pixel — but the priority is
explicit, not silent.

**Robustness.** Source pixels for which neither L1B CTH nor the pressure
ratio yields a physical height are dropped and counted. If more than
`max_drop_frac = 10 %` of source pixels in a granule are dropped, the whole
granule fails (we refuse to invent heights). In practice the drop fraction
is typically 1–3 % per granule.

### 4.2 Shadow projection: Bresenham line, not a polygon

**Source:** DARCLOS projects the four cloud-pixel corners along the sun
direction and rasterizes the resulting *quadrilateral* on the ground; every
candidate pixel inside that quadrilateral is PCSF.

**Our choice:** We project only the cloud pixel **centre** along the sun
direction (DARCLOS Eqs. 2–7), find the nearest grid pixel to the projected
shadow tip, and mark every pixel on a Bresenham line from the cloud centre
to that tip as potentially shadowed (excluding the cloud pixels themselves).

**Why a line, not a polygon.** We initially implemented the full polygon
projection (see the prototype `notebooks/DARCLOS_TEMPO_implementation.ipynb`
and the all-improvements `Cloud_Shadows_v2.ipynb`) and it produced visibly
*worse* results than the line: per-cloud-pixel umbra polygons came out
roughly one TEMPO-pixel wide, which combined with the strict radiometric
filter created sparse, fragmented shadow masks. The line — though
geometrically incomplete — better captures the spatial *extent* of a
shadow because it traverses every pixel between the cloud and the projected
tip, and the radiometric filter then keeps the ones that are actually dark.
Future work should revisit the polygon approach with proper umbra-cluster
dissolution; see Section 7.

**Implementation detail.** The projection is fully vectorized — one NumPy
expression computes `(d_lat, d_lon)` for every cloud pixel at once. The
nearest-pixel lookup uses a single `scipy.spatial.cKDTree.query` over all
projected shadow tips simultaneously. The Bresenham line drawing is the only
remaining per-pixel loop, because it writes into a shared mask.

### 4.3 Radiometric confirmation: ECF as an ACSF surrogate

This is the most consequential — and most TEMPO-specific — change.

**Source:** DARCLOS computes SCNLER from TEMPO L1B radiances using a
Rayleigh-correction look-up table, then compares it to a DLER climatology
at 13+ wavelengths.

**Our choice:** We mark a PCSF pixel as actually shadowed when the CLDO4
retrieved effective cloud fraction is below a small threshold:

```
ACSF  ⇔  pixel is in PCSF  AND  ECF < shadow_threshold = 0.05
```

**Why this works.** Look at how ECF is defined in the TEMPO CLDO4 algorithm
(Wang et al., 2025, Section 3.2). The retrieval inverts

```
I_meas(466 nm) = I_clear(GLER, SZA, VZA, ...) · (1 − f) + I_cloud · f
```

for the cloud fraction `f`, where `I_clear` is the modelled TOA radiance for
a *clear* pixel over a Lambertian surface with reflectance equal to GLER.
If the pixel is clear but shadowed, the measured radiance `I_meas` is
smaller than `I_clear` (the surface is darker than GLER predicts), so the
inversion drives `f` toward 0 or negative — exactly the "darker than the
GLER climatology" signal that DARCLOS' Γ < −15 % criterion is supposed to
detect.

In other words: the CLDO4 cloud-fraction retrieval already encodes the
"is this pixel darker than expected from the surface alone?" question. We
just read it off instead of re-implementing the comparison from raw L1B
radiances.

**What we give up.** Single-wavelength refinement (466 nm only), no SCSF
flags, no rigorous calibration of the −15 % threshold. We gain a much
simpler pipeline that only needs CLDO4 L2 fields, no LUTs, and no DLER
climatology.

### 4.4 Geometry: solar/viewing angles from L1B

The DARCLOS notebook documented that in the V03 CLDO4 product
`viewing_azimuth_angle` is entirely fill-valued and `solar_azimuth_angle` is
~94 % fill. The earlier Debug notebook used those L2 angles silently — NaNs
propagated through the projection, `np.argmin` returned grid index 0, and
each cloud pixel drew a spurious Bresenham line to the granule corner. The
result *looked* roughly plausible because the spurious lines crossed enough
genuinely dark regions to give the AND-with-low-ECF filter something to
latch on to.

The pipeline reads **all four angles** from the L1B `band_290_490_nm` group
instead, which is fully populated. It also raises if any of the four is
entirely fill-valued in a given L1B file — we'd rather fail loudly than
fabricate geometry.

### 4.5 Scaling: one Python process, one day

Each invocation of `scripts/run_day.py` processes one day's worth of
granules sequentially. With the vectorized projection and KDTree-based
nearest-pixel lookup, a full day (~80–110 granules) finishes in a few
minutes on one core. Multi-day backfills are achieved by external job
arrays — Slurm, GNU Parallel, or a simple bash loop. The script does not
spawn its own workers because the bottleneck (granule I/O over NFS) is
typically I/O-bound rather than CPU-bound, and external parallelism gives
better isolation, simpler logging, and easier failure recovery.

---

## 5. Pipeline implementation

The code lives in `preprocess_shadows/scripts/` and follows the project's
"fail loudly, explicit configuration" principles from `CLAUDE.md`.

```
scripts/
├── shadows.py     — pure-NumPy algorithm: heights, projection, masks
├── io_utils.py    — HDF5/NetCDF reading, GeoTIFF + shapefile writing
└── run_day.py     — CLI orchestrator
configs/
└── day_example.yaml
```

### 5.1 What each module does

- **`shadows.py`** is pure algorithm: takes arrays in, produces masks out.
  `ShadowParams` is the immutable parameter container. `compute_masks()` is
  the orchestrator — it returns `(cloud_mask, potential_mask, actual_mask,
  diag)` for one granule plus a diagnostics dict for the run-time log. No
  file I/O.
- **`io_utils.py`** handles all the data-plumbing:
  - File pairing by parsing the `<timestamp>_S<scan>G<granule>` token out of
    filenames.
  - L1B reading via `h5py` directly. We learned the hard way that
    `netCDF4.Dataset` fails with `[Errno -101] NetCDF: HDF error` on shared
    NFS storage; `h5py` opens the same files fine.
  - L2 reading also via `h5py` for the same reason.
  - GeoTIFF writing follows the convention in
    `test/netcdf_to_raster_with_L2.py`: transpose+flip, gamma-correct the
    RGB channels, derive a bounding-box affine transform from the granule's
    lat/lon corners.
  - Shapefile writing uses `fiona` directly (not `GeoDataFrame.to_file`)
    because the latter calls `np.array(geom, copy=False)`, which is no
    longer permitted under NumPy 2.0.
- **`run_day.py`** is the CLI: load the YAML config, glob the L1B day
  directory, pair each L1B with its L2, run `compute_masks`, write the
  GeoTIFF and three shapefiles, log per-granule diagnostics, summarize.

### 5.2 Configuration

A complete config (see `configs/day_example.yaml`) has three blocks:

| Block | Keys |
|---|---|
| **Date** | `year`, `month`, `day` |
| **Paths** | `base_path`, `version`, `l1_dir_template`, `l2_dir_template`, `l1_band`, `output_root` |
| **Algorithm** | `cloud_threshold`, `shadow_threshold`, `safety_factor_c`, `h_scale_m`, `h_cap_m`, `max_drop_frac`, `apply_gamma`, `gamma` |

Algorithm defaults reproduce the v3 vectorized notebook exactly. Every
constant is named, documented and traceable to either Trees et al. (2022)
or Wang et al. (2025).

### 5.3 Outputs

Per granule, in `{output_root}/{year}/{month}/{day}/`:

| File | Content |
|---|---|
| `rgb_<basename>.tif` | 3-band uint8 GeoTIFF, EPSG:4326, gamma-corrected RGB |
| `<basename>_clouds.shp` | Polygons where `ECF ≥ 0.30` |
| `<basename>_potential_shadows.shp` | PCSF polygons (geometric step) |
| `<basename>_actual_shadows.shp` | ACSF polygons (`PCSF ∩ ECF < 0.05`) |

All four files share the same affine transform, so loading them together in
QGIS overlays cleanly.

### 5.4 Failure handling

| Condition | Behaviour |
|---|---|
| No matching L2 for an L1B granule | Warn, skip, count in summary |
| L1B angle entirely fill-valued | `ValueError` for that granule; others continue |
| Height-drop fraction > `max_drop_frac` | `ValueError` for that granule |
| HDF5 open error on NFS | Suggest `HDF5_USE_FILE_LOCKING=FALSE` |

The pipeline never silently substitutes default values for missing inputs.

---

## 6. Outputs and how to read them

The three shapefiles are nested by construction:

- **`actual_shadows ⊆ potential_shadows`** — every ACSF polygon is inside a
  PCSF polygon by definition.
- **`clouds` is disjoint from both** — cloud pixels are excluded from PCSF
  when the Bresenham line is rasterized.

A pixel that is *neither* cloud nor in any shadow shapefile is, by this
pipeline's definition, treated as background.

The recommended quality flag for downstream consumers is **`actual_shadows`**:
PCSF alone is too inclusive (it flags many clear pixels that happen to lie
along the projection line), and the cloud polygons are simply the CLDO4 ECF
re-expressed as polygons.

---

## 7. Limitations

The pipeline is operational and visually validated against RGB composites
on a small sample of granules. It is *not* yet validated quantitatively
against an independent ground truth (e.g. GOES-East ABI), and the
limitations below reflect both that gap and the design simplifications we
made on the way.

### 7.1 Theoretical / algorithmic

**False positives over intrinsically dark surfaces.** The ACSF surrogate
fires whenever `ECF < 0.05`. Over open water (GLER466 ~ 0.03–0.05),
sunglint margins, and dense aerosol plumes, ECF is naturally low without
any shadow being present. Whenever the geometric PCSF projection happens
to cross such a region, the pipeline will register a spurious actual
shadow. This is the single biggest precision risk.

**False negatives over bright surfaces.** Conversely, over snow, ice,
deserts and dry-season vegetation where GLER466 is high, even a real cloud
shadow will not push ECF below 0.05 — the surface is bright enough that the
darkened observation still exceeds the threshold. Shadow detection over
snow is genuinely difficult, even for DARCLOS proper.

**Height bias for thick convection.** OCP is a radiative centroid, not the
geometric cloud top. For optically thick clouds (deep convection,
thunderstorms), the geometric top can be several kilometres above OCP, so
our height underestimates the true cloud top and the projection
underestimates the shadow length. The safety factor `C = 0.5` partially
absorbs this but does not eliminate it.

**No SZA cutoff.** The algorithm runs for any solar zenith angle, even
above ~80° where shadows extend tens of kilometres and the projection
becomes geometrically unstable. The TEMPO L2 QA convention is `SZA < 75°`;
applying that filter is in the roadmap.

**No snow / quality masking.** Pixels with `snow_ice_fraction > 0.5` or
non-zero `processing_quality_flag` error bits are currently processed
regardless. Adding these filters would tighten precision at the edges of
the scan and over winter scenes.

**Single-wavelength radiometric check.** We use ECF at 466 nm as the
radiometric surrogate. A multi-wavelength check (e.g. SceneLER at 440 and
466 nm) would help discriminate aerosol plumes (which darken 440 nm more
than 466 nm) from shadows (which darken both roughly equally). The current
pipeline cannot make that distinction.

**Line vs polygon shadow footprint.** The Bresenham line catches shadow
*length* well but understates *width*. Real umbras are one to two TEMPO
pixels wide cross-track; the line is one pixel wide. The omission is small
in pixel count but real.

**Hypsometric height with constant scale height.** A constant `H_SCALE =
8500 m` has ~10 % error in the tropics versus high-latitude winter. A
co-located MERRA-2 profile would close this gap; the infrastructure is
not in place.

**Aliased smokes and dust.** The TEMPO cloud paper (Wang et al. 2025,
§ 3.1) documents that wildfire smoke is sometimes retrieved as ECF ≈ 0.5+.
Such a "cloud" entry will project a shadow that is, in reality, the
shadow of the smoke plume itself superimposed on its own darkened ground.
The pipeline does not currently distinguish smoke from cloud.

### 7.2 Implementation

**No quantitative validation against an external ground truth.** We have
visually inspected outputs for a small number of granules and found them
plausible. We have not computed precision, recall or F₁ against GOES-East
ABI true-colour imagery, which is the recommended next step (cf.
[`DARCLOS-TEMPO.md`](DARCLOS-TEMPO.md) § 3.6).

**Azimuth-convention assumption.** The projection formula assumes the TEMPO
L1B `solar_azimuth_angle` follows the geographic convention (from North,
clockwise, sun direction). The Bresenham line in this pipeline is
forgiving of sign errors here, but if the convention is different from
what we assumed, all shadows would be projected on the wrong side of the
cloud and the AND-with-ECF<0.05 filter would still find some matches by
coincidence — producing visually-plausible but geometrically-wrong results.
A synthetic ground-truth test (one isolated cumulus, project its shadow,
check it lands on the visibly dark patch in the RGB) has not yet been run.

**Bounding-box GeoTIFF transform.** TEMPO's swath is not rectilinear in
lat/lon; the affine transform derived from `from_bounds(west, south, east,
north, width, height)` introduces small but real geometric distortion
near the granule edges (≲ 1 pixel in our experience). This affects both
the GeoTIFF and the shapefiles. For pixel-accurate georeferencing the
right path is GCP-based warping with `latitude_bounds`/`longitude_bounds`,
which is not implemented.

**Always-overwrite policy.** Each invocation re-runs and overwrites all
outputs for the configured day. There is no resume / skip-existing logic
on purpose: it makes algorithm changes easier to verify. For very large
backfills, callers must implement their own resume logic externally.

**Cloud-source threshold tied to cloud-class threshold.** A single
`cloud_threshold` (0.30) defines both which pixels cast shadows *and* which
pixels are output as cloud-class. Decoupling these (e.g., source `≥ 0.30`,
class `≥ 0.20` to align with the TEMPO QA filter) would let the algorithm
catch shadows from thinner cumulus without changing the labels exposed to
downstream training.

**No L1B `cloud_mask_group` cross-check.** L1B carries its own quick-look
cloud mask from GOES-East ABI co-registration. We do not currently use it
to filter or cross-check the CLDO4 ECF mask.

**Vectorization stops at the line drawing.** The Bresenham raster pass
remains a per-source-pixel Python loop. For ~10⁵ source pixels per granule
this is acceptable (seconds), but it is the next obvious optimization
target if the pipeline is run on a much larger scale.

---

## 8. Recommended next steps

In rough order of expected scientific payoff:

1. **GOES-East validation.** Compute precision/recall/F₁ on a curated
   sample of granules against ABI true-colour. This is the single missing
   piece for trustworthy operational use.
2. **Add quality masking.** SZA < 75°, `snow_ice_fraction ≤ 0.5`, and
   `processing_quality_flag` error bits.
3. **Brightness gate for ACSF.** Require `GLER466 > δ` (e.g. 0.05) before
   firing ACSF; this is the cheapest available defence against ocean and
   aerosol false positives.
4. **Dilate the Bresenham line by ±1 pixel cross-track.** Approximates the
   correct umbra width without going to full polygons.
5. **Decouple `cloud_source` and `cloud_class` thresholds.** Allow ECF
   ≥ 0.20 as a shadow caster while keeping ECF ≥ 0.30 as the cloud label.
6. **GCP-based GeoTIFF georeferencing.** Use `latitude_bounds`/
   `longitude_bounds` to produce pixel-accurate warped output.
7. **MERRA-2 height profiles.** Replace the constant scale height with a
   co-located profile to reduce height bias at high latitudes / strong
   inversions.

---

## 9. References

- Trees, V. J. H., Wang, P., & Stammes, P. (2022). DARCLOS: a cloud shadow
  detection algorithm for TROPOMI. *Atmospheric Measurement Techniques*,
  15, 3121–3140. doi:10.5194/amt-15-3121-2022.
- Wang, H., Nowlan, C. R., González Abad, G., et al. (2025). Algorithm
  Theoretical Basis for Version 3 TEMPO O₂–O₂ Cloud Product. *Earth and
  Space Science*, 12, e2024EA004165. doi:10.1029/2024EA004165.
- Zoogman, P., et al. (2017). Tropospheric Emissions: Monitoring of
  Pollution (TEMPO). *JQSRT* 186, 17–39.
- Companion documents in this folder:
  - [`DARCLOS-TEMPO.md`](DARCLOS-TEMPO.md) — science motivation and the
    full DARCLOS-vs-TEMPO design discussion.
  - [`TEMPO_pipeline.md`](TEMPO_pipeline.md) — overview of the TEMPO
    L0→L1B→L2→L3 processing chain.
  - [`data_structure.md`](data_structure.md) — L1B and L2 variable
    inventory.
