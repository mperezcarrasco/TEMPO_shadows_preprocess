# TEMPO Data Structure Reference

All data files are NetCDF4 and follow the CF-1.6 / ACDD-1.3 conventions. They share a common spatial grid: **132 mirror steps (along-track) × 2048 cross-track pixels**, covering a single granule (~6.7 minutes of a TEMPO east-west scan). Four granules are available from 2025-09-09, spanning two different scan numbers and local times:

| Filename token | Scan | Granule | Start time (UTC) | Notes |
|---|---|---|---|---|
| `S002G02` | 2 | 2 | 11:52:02 | Morning, high SZA (~66–77°) |
| `S002G03` | 2 | 3 | 11:58:42 | Morning, high SZA |
| `S003G05` | 3 | 5 | 12:52:05 | Late morning |
| `S014G02` | 14 | 2 | 23:12:18 | Near-terminator, very high SZA |

---

## 1. Level 1B Radiance (`raw_l1/`)

**Files:** `TEMPO_RAD_L1_V04_<timestamp>_<scan_gran>.nc`  
**Processing version:** V04 (SDPC v4.6.1)  
**Spatial coverage (S002G02):** 17.2°–60.6°N, 77.9°–46.0°W

### File Organization

L1B files are organized into three top-level groups and one spectral group pair:

```
/ (root)
├── granule_flag          — overall granule processing status
├── mirror_step (132,)    — scan mirror position index (along-track dimension)
├── time (132,)           — exposure start time [s since 1980-01-06]
├── exposure_time (132,)  — integration duration [s]
├── earth_sun_distance    — scalar Earth–Sun distance [m] used for irradiance normalization
│
├── band_290_490_nm/      — UV detector: 292–495 nm
├── band_540_740_nm/      — VIS detector: 538–741 nm
├── geometry/             — spacecraft and solar position vectors
├── cloud_mask_group/     — quick-look cloud mask from L1B INR step
└── inr_input/            — Image Navigation and Registration telemetry
```

### Spectral Band Groups (UV and VIS, identical structure)

Each spectral group contains the core radiance data. The **spectral dimension** has 1028 pixels, corresponding to the CCD column axis.

| Variable | Shape | Units | Description |
|---|---|---|---|
| `radiance` | (132, 2048, 1028) | photons/s/cm²/nm/sr | Calibrated top-of-atmosphere spectral radiance. This is R_meas(λ) in the DARCLOS SCNLER equation. Each spectrum covers the full band at ~0.2 nm/pixel sampling. |
| `radiance_error` | (132, 2048, 1028) | photons/s/cm²/nm/sr | 1-σ photon noise uncertainty on each radiance pixel. |
| `nominal_wavelength` | (2048, 1028) | nm | Wavelength assigned to each CCD pixel, per across-track position. Varies slightly along the slit due to optical distortion. UV range: 292–495 nm; VIS: 538–741 nm. |
| `longitude` | (132, 2048) | degrees_east | Pixel center geodetic longitude. |
| `latitude` | (132, 2048) | degrees_north | Pixel center geodetic latitude. |
| `longitude_bounds` | (132, 2048, 4) | degrees_east | Corner longitudes (NE, NW, SW, SE) — defines the exact pixel footprint. |
| `latitude_bounds` | (132, 2048, 4) | degrees | Corner latitudes. |
| `terrain_height` | (132, 2048) | m | Area-weighted mean terrain elevation from GMTED2010. Needed as h_sfc in the DARCLOS shadow projection formula. |
| `terrain_height_stddev` | (132, 2048) | m | Subpixel terrain roughness — indicates whether the pixel spans heterogeneous topography. |
| `solar_zenith_angle` | (132, 2048) | degrees | SZA at pixel center and observation time. Primary control on shadow length: tan(SZA) sets the horizontal shadow offset. |
| `solar_azimuth_angle` | (132, 2048) | degrees | SAA at pixel center. Controls shadow direction: sin(SAA) and cos(SAA) determine the E–W and N–S shadow displacement. |
| `viewing_zenith_angle` | (132, 2048) | degrees | VZA at pixel center. Fixed per pixel for TEMPO (geostationary); used in DLER climatology lookup. |
| `viewing_azimuth_angle` | (132, 2048) | degrees | VAA at pixel center. Also fixed per pixel for TEMPO. |
| `snow_ice_fraction` | (132, 2048) | — | Fraction of pixel covered by snow/ice from IMS. Relevant for interpreting anomalously high scene reflectance. |
| `cloud_top_height` | (132, 2048) | m | Cloud top height from GOES-East ABI (via INR registration). In the present files this field is entirely fill-valued; OCP-based height conversion from L2 is required instead. |
| `ABI_Band_1_East` / `ABI_Band_2_East` | (132, 2048) | photons/s/cm²/nm/sr | Spectrally equivalent GOES-East ABI radiance co-registered to TEMPO pixels. Useful for cloud mask cross-validation. |
| `inr_quality_flag` | (132, 2048) | — | Image navigation quality; affects geolocation accuracy. |
| `pixel_quality_flag` | (132, 2048, 1028) | — | Per-spectral-pixel bitwise flag (bad/hot pixels, saturation). Used to exclude bad spectral samples from SCNLER computation. |
| `ground_pixel_quality_flag` | (132, 2048) | — | Aggregate pixel quality over the spatial footprint. |

### Cloud Mask Group

| Variable | Shape | Description |
|---|---|---|
| `cloud_mask` | (132, 2048) | Binary cloud flag from L1B quick-look (0 = clear, 1 = cloudy). ~26% cloud cover in S002G02. This is a coarse mask; CLDO4 ECF from L2 is the authoritative cloud product. |
| `red`, `green`, `blue` | (132, 2048) | Derived true-color imagery for visualization. |

### Geometry Group

Contains spacecraft position (X,Y,Z) and solar position vectors in Earth-centered coordinates, used internally for precise geometric calculations. Not needed directly for the shadow algorithm.

---

## 2. Level 2 CLDO4 Cloud Product — V03 (`raw_l2_v3/`)

**Files:** `TEMPO_CLDO4_L2_V03_<timestamp>_<scan_gran>.nc`  
**Algorithm:** O₂-O₂ absorption at 477 nm (IPA framework)

### File Organization

```
/ (root)
├── xtrack (2048,)     — cross-track pixel index
├── mirror_step (132,) — along-track mirror step index
│
├── product/           — primary retrieved quantities
├── geolocation/       — angles and coordinates
├── support_data/      — intermediate retrieval quantities
└── qa_statistics/     — fit diagnostics
```

### `product/` Group — Primary Retrievals

| Variable | Shape | Units | Description |
|---|---|---|---|
| `cloud_fraction` | (132, 2048) | — | **Effective Cloud Fraction (ECF)** at 466 nm. The fraction of the pixel that, under the IPA, is modeled as fully overcast with a Lambertian cloud albedo of 0.8. Values range 0–1. The standard quality filter for trace gas retrievals is ECF < 0.2 (clear enough for retrieval) and ECF ≥ 0.2 (cloudy, use as shadow source). **In V03, ECF has a known positive bias (~0.05–0.1); clear-sky pixels show ECF ≈ 0.05 rather than ≈ 0.** |
| `cloud_pressure` | (132, 2048) | hPa | **Optical Centroid Pressure (OCP)**. The effective pressure level at which the cloud appears to reflect photons, retrieved from O₂-O₂ SCD. This is the primary cloud height proxy. Must be converted to physical altitude (via a pressure-height profile) for the DARCLOS shadow projection. Range: 55–1200 hPa. |
| `CloudRadianceFraction466` | (132, 2048) | — | Radiative cloud fraction at 466 nm — the cloud fraction weighted by the ratio of cloudy-to-clear radiance. This is fcr used in the NO₂ AMF, which differs from ECF. |
| `CloudRadianceFraction440` | (132, 2048) | — | Same at 440 nm (the NO₂ AMF evaluation wavelength). |
| `processing_quality_flag` | (132, 2048) | — | 16-bit bitwise flag for retrieval-specific issues (e.g., failed convergence, out-of-range OCP, snow/ice interference). |

### `geolocation/` Group

Identical in content to the L1B geolocation: `latitude`, `longitude`, `solar_zenith_angle`, `solar_azimuth_angle`, `viewing_zenith_angle`, `viewing_azimuth_angle`, `relative_azimuth_angle`, pixel corner coordinates, and `time`. These are the authoritative geolocation fields to use for the shadow algorithm (collocated with the L2 retrievals).

### `support_data/` Group — Intermediate Quantities

| Variable | Shape | Units | Description |
|---|---|---|---|
| `GLER466` | (132, 2048) | — | **Geometry-dependent Lambertian Equivalent Reflectance at 466 nm** from MODIS BRDF climatology (land) or Cox-Munk model (ocean). This is the surface reflectance used in the CLDO4 forward model. Analogous to the DLER in DARCLOS, though only at two wavelengths. |
| `GLER440` | (132, 2048) | — | GLER at 440 nm. |
| `SceneLER466` | (132, 2048) | — | **Scene Lambertian Equivalent Reflectance at 466 nm** — the effective reflectance of the observed scene, derived from the measured radiance. This is A_scene(466 nm) in the DARCLOS framework: the key quantity compared against the DLER climatology to detect shadow darkening. |
| `SceneLER440` | (132, 2048) | — | SceneLER at 440 nm. |
| `SurfaceLER466` | (132, 2048) | — | Scene LER computed at terrain (surface) pressure — a diagnostic for understanding surface contributions vs. atmospheric path effects. |
| `ScenePressure` | (132, 2048) | hPa | The effective pressure level of the scene reflectance. |
| `TerrainPressure` | (132, 2048) | hPa | Terrain-corrected surface pressure at each pixel, accounting for GMTED2010 elevation. |
| `surface_pressure` | (132, 2048) | hPa | Model surface pressure from GEOS-CF. |
| `terrain_height` | (132, 2048) | m | GMTED2010 terrain height (same as in L1B). |
| `SlantColumnAmountO2O2` | (132, 2048) | 10⁴³ molec² cm⁻⁵ | O₂-O₂ slant column density used for OCP retrieval. The SCD is sensitive to photon penetration depth and thus to cloud altitude. |
| `fitted_slant_column` | (132, 2048) | 10⁴³ molec² cm⁻⁵ | O₂-O₂ SCD at reference temperature (223K), after temperature correction. |
| `fitted_slant_column_uncertainty` | (132, 2048) | 10⁴³ molec² cm⁻⁵ | 1-σ uncertainty on the fitted SCD. |
| `snow_ice_fraction` | (132, 2048) | — | IMS snow/ice fraction (same as L1B). |
| `nonclipped_cloud_fraction` | (132, 2048) | — | ECF before clipping to [0, 1]. Useful for diagnosing retrieval artifacts. |
| `nonclipped_cloud_pressure` | (132, 2048) | hPa | OCP before clipping. |
| `SCD_MainDataQualityFlags` | (132, 2048) | — | Quality flag for the SCD fit. 0 = good. |
| `ReflectanceFactor466` | (132, 2048) | — | Measured top-of-atmosphere reflectance at 466 nm: π·R_meas / (I₀·cos(SZA)). |
| `O2O2CloudTemperature` | (132, 2048) | K | Effective atmospheric temperature used in O₂-O₂ SCD correction. |

---

## 3. Level 2 CLDO4 Cloud Product — V04 (`raw_l2_v4/`)

**Files:** `TEMPO_CLDO4_L2_V04_<timestamp>_<scan_gran>.nc`

V04 has an **identical group/variable structure** to V03. The schema, dimensions, and variable names are the same. The only meaningful differences are in the retrieved values:

| Metric | V03 | V04 | Delta |
|---|---|---|---|
| ECF mean (S002G02) | 0.379 | 0.301 | −0.078 |
| ECF mean (S002G03) | 0.385 | 0.292 | −0.093 |
| ECF mean (S003G05) | 0.349 | 0.260 | −0.089 |
| ECF mean (S014G02) | 0.317 | 0.237 | −0.081 |

V04 corrects the systematic positive ECF bias documented in V03 (Wang et al., 2025). In V03, clear-sky pixels showed ECF ≈ 0.05 instead of ≈ 0, attributed to overestimation of absolute L1B radiance and inaccuracies in the GLER climatology. V04 reduces this bias, bringing ECF distributions closer to the expected physical range. **For all shadow detection work, V04 should be the primary dataset.** V03 is retained for algorithm sensitivity analysis (e.g., testing whether shadow candidate selection is sensitive to ECF version).

OCP distributions are nearly identical between versions (mean difference < 1 hPa), since the OCP retrieval depends primarily on the O₂-O₂ SCD rather than the reflectance calibration.

---

## 4. Variables Relevant to Cloud Shadow Detection

The following table summarizes the variables directly needed by the DARCLOS-TEMPO algorithm, with their source file and role.

### Required Inputs

| Variable | Source | Group | Role in DARCLOS-TEMPO |
|---|---|---|---|
| `cloud_fraction` | L2 V04 | `product/` | Identifies cloudy pixels (ECF ≥ 0.2) as shadow sources and clear pixels (ECF < 0.05) as shadow candidates |
| `cloud_pressure` | L2 V04 | `product/` | **OCP → cloud height conversion.** Input to h_c = z(p = OCP) via MERRA-2 profile; drives shadow projection length |
| `solar_zenith_angle` | L2 V04 | `geolocation/` | Controls shadow length: tan(SZA) × h is the horizontal shadow offset |
| `solar_azimuth_angle` | L2 V04 | `geolocation/` | Controls shadow direction: sin(SAA) → E–W, cos(SAA) → N–S displacement |
| `viewing_zenith_angle` | L2 V04 | `geolocation/` | Used to query DLER climatology at correct geometry (fixed per pixel for GEO) |
| `viewing_azimuth_angle` | L2 V04 | `geolocation/` | Same as above |
| `latitude` / `longitude` | L2 V04 | `geolocation/` | Pixel center coordinates for spatial shadow projection and DLER lookup |
| `latitude_bounds` / `longitude_bounds` | L2 V04 | `geolocation/` | Pixel corner coordinates for polygon containment test (PCSF step) |
| `terrain_height` | L2 V04 | `support_data/` | h_sfc in shadow height formula: h = (1+C)(h_c − h_sfc) |
| `SceneLER466` / `SceneLER440` | L2 V04 | `support_data/` | A_scene proxy at 440/466 nm — starting point for contrast calculation against DLER climatology |
| `GLER466` / `GLER440` | L2 V04 | `support_data/` | Surface reflectance used in CLDO4; can be compared to DLER climatology |
| `radiance` (UV band) | L1B V04 | `band_290_490_nm/` | R_meas(λ) at DARCLOS wavelengths (328–494 nm) for full SCNLER computation |
| `radiance` (VIS band) | L1B V04 | `band_540_740_nm/` | R_meas(λ) at VIS wavelengths (538–741 nm) for λ_max determination |
| `nominal_wavelength` (UV) | L1B V04 | `band_290_490_nm/` | Maps CCD pixel index to wavelength; needed to extract R_meas at specific DARCLOS wavelengths |
| `nominal_wavelength` (VIS) | L1B V04 | `band_540_740_nm/` | Same for VIS band |
| `processing_quality_flag` | L2 V04 | `product/` | Mask pixels with bad retrievals before flagging |
| `SCD_MainDataQualityFlags` | L2 V04 | `support_data/` | Exclude pixels with poor SCD fits from the ACSF computation |

### Useful Diagnostics and Ancillaries

| Variable | Source | Group | Purpose |
|---|---|---|---|
| `snow_ice_fraction` | L2 V04 | `support_data/` | Flag snow/ice pixels — shadow detection is unreliable over bright, spectrally flat surfaces |
| `nonclipped_cloud_fraction` | L2 V04 | `support_data/` | Detect saturated retrievals (nonclipped ≫ 1.0) that indicate retrieval breakdown |
| `cloud_mask` | L1B V04 | `cloud_mask_group/` | Quick-look consistency check against CLDO4 ECF |
| `ABI_Band_1_East` | L1B V04 | `band_290_490_nm/` | GOES-East visible imagery co-registered to TEMPO grid — primary validation reference for shadow flags |
| `fit_rms_residual` | L2 V04 | `qa_statistics/` | High RMS may indicate spectral contamination or retrieval instability |
| `fit_convergence_flag` | L2 V04 | `qa_statistics/` | Pixels where the ECF–OCP iteration did not converge should be excluded |
| `O2O2CloudTemperature` | L2 V04 | `support_data/` | Diagnostic for temperature correction accuracy; relevant for deep convective clouds |

### Variables NOT Needed (for this algorithm)

- `inr_input/` group (raw telemetry, only for L1B production)
- `geometry/` group (spacecraft vectors, not needed once SZA/SAA are computed)
- `SlantColumnSceneO2O2`, `SlantColumnTerrainO2O2` (internal CLDO4 diagnostics)
- `ecf_niter`, `ocp_niter` (iteration counts, diagnostic only)

---

## 5. Dimension Convention

All spatial arrays use the convention `(mirror_step, xtrack)` = **(132, 2048)**, where:
- `mirror_step` (132) is the **along-track** (N–S) dimension — each step represents one 6.7-minute exposure covering a ~1° N-S slit position.
- `xtrack` (2048) is the **cross-track** (approximately E–W) dimension — the 2048 CCD rows along the instrument slit.

Spectral arrays have an additional trailing dimension of 1028 (spectral pixels per CCD column).

The spatial resolution at field center is approximately **2.0 km (N-S) × 4.75 km (E–W)**.
