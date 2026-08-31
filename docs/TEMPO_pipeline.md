# TEMPO Data Processing Pipeline

**Mission:** TEMPO (Tropospheric Emissions: Monitoring of Pollution)
**Instrument:** UV/Vis imaging grating spectrometer aboard Intelsat-40e (91°W GEO)
**Processing center:** SAO Science Data Processing Center (SDPC), Smithsonian Astrophysical Observatory
**Distribution:** NASA Atmospheric Science Data Center (ASDC) at Langley Research Center
**Current version:** Version 3 (V03, released May 20, 2024)

---

## Pipeline Overview

```
Raw telemetry
     ↓
  [ L0 ]  Raw digital counts + housekeeping
     ↓
  [ L1B ] Calibrated spectral radiances + geolocation
     ↓
  [ L2 Clouds (CLDO4) ]  Effective Cloud Fraction + Optical Centroid Pressure
     ↓
  [ L2 Trace Gases ]  NO₂, O₃, HCHO, SO₂, BrO, H₂O column retrievals
     ↓
  [ L3 ]  Gridded products (one file per hourly full-scan)
```

The cloud retrieval (CLDO4) must always precede trace gas retrievals because cloud fraction and cloud pressure are required inputs to the air mass factor (AMF) calculation. The stratosphere-troposphere separation step in the NO₂ retrieval runs only after all 9 granules of one complete hourly scan are available.

---

## Level 0 (L0): Raw Telemetry

### Purpose
Ingest and packetize raw spacecraft downlink data. L0 represents the unprocessed data as transmitted from the TEMPO instrument aboard Intelsat-40e.

### Inputs
- Raw downlink telemetry packets from TEMPO spacecraft
- Housekeeping data: instrument temperatures, mechanism positions, power states
- Timing and attitude data from spacecraft

### What the data contains
- Raw digital counts (DN) from the two 2D CCD detectors: 2048 (spatial) × 1028 (spectral) pixels for UV band (~293–494 nm) and VIS band (~538–741 nm)
- No calibration applied — values are in raw engineering units
- Scan Mechanism Assembly (SMA) position (which of the 1181 E/W mirror steps is active)
- Calibration Mechanism Assembly (CMA) wheel position (nadir / working diffuser / reference diffuser / dark current)

### Measurement types
TEMPO produces three types of raw spectral measurements that feed into L1B:

**Earth-view radiance:** CMA in nadir position; SMA steps sequentially through all 1181 E/W mirror positions, each position recording a 1D spectral image of a ~1° N/S slice of the Earth through the slit.

**Solar irradiance:** CMA rotated to working diffuser or reference diffuser; sun viewed through a diffuse reflector to produce a spatially uniform, high-SNR solar reference spectrum used for radiometric and spectral calibration.

**Dark current:** CMA in dark position; records CCD dark signal (thermally generated electrons) for subtraction during radiometric calibration.

### Outputs
- Raw telemetry archive; time-ordered CCD readout frames with associated metadata

---

## Level 1B (L1B): Calibrated Spectral Radiances

### Purpose
Convert raw detector counts to physically calibrated spectral radiances and irradiances with full geolocation. L1B data products are the starting point for all science retrievals.

### Inputs
- L0 raw digital counts (Earth-view, solar irradiance, dark current frames)
- Pre-launch instrument characterization: radiometric response, slit function measurements, pixel wavelength mapping
- On-orbit solar irradiance measurements (through working and reference diffusers)
- Spacecraft attitude and orbit determination (from Intelsat-40e)
- GOES-East imagery (for image navigation and registration)

### Processing steps

**Dark current subtraction:** The dark current frame (measured with shutter closed) is subtracted from each Earth-view and solar frame to remove the thermally generated CCD signal. Dark current is temperature-dependent and measured regularly.

**Radiometric calibration:** Raw counts are converted to absolute spectral radiance (Earth view) or irradiance (solar view) using the instrument's pre-launch calibration coefficients, corrected for on-orbit throughput degradation tracked by comparing working diffuser solar measurements over time. Output units: radiance in W/cm²/sr/nm; irradiance in W/cm²/nm.

**Spectral calibration (wavelength assignment):** Each CCD pixel is assigned a precise wavelength value. Pre-launch laboratory measurements establish the initial wavelength-to-pixel mapping, which may drift on orbit due to thermal and mechanical effects. On-orbit spectral calibration is performed by fitting the measured solar irradiance spectrum against the high-resolution TSIS-1 (Total and Spectral Solar Irradiance Sensor-1) solar reference spectrum. A super-Gaussian slit function is fit:

SL(λ) ∝ exp(−0.5 × |λ/w|^k)

with width (w), shape (k), and asymmetry (αw) as free parameters, plus a wavelength shift. This fit is performed independently for each of the 2048 along-slit (across-track) pixel positions to account for spatial variation in the instrument's optical point spread function.

**Image Navigation and Registration (INR):** Precise geolocation assigns each spatial pixel an Earth surface latitude and longitude, along with solar zenith angle (SZA), viewing zenith angle (VZA), relative azimuth angle (RAA), and pixel corner coordinates. INR uses a Kalman filter that combines spacecraft attitude knowledge with tie-point registration against GOES-East satellite imagery. GOES provides a stable geometric reference because its orbital position is accurately known, so cross-correlating TEMPO's radiance images with co-registered GOES images corrects residual pointing errors.

### Outputs
- **L1B Radiance product (RAD_L1B):** Calibrated Earth-view spectral radiances on the native pixel grid. Contains: radiance spectra [W/cm²/sr/nm], wavelength arrays, geolocation (lat/lon/SZA/VZA/RAA/pixel corners), quality flags.
- **L1B Irradiance product (IRR_L1B):** Calibrated solar irradiance spectra from working and reference diffusers. Used as the reference solar spectrum (I₀) in all DOAS retrievals.

### Key product characteristics
- Spatial resolution: ~2.0 km (N/S) × 4.75 km (E/W) at field center
- Full FOR: ~170°W to ~10°W, ~10°N to ~70°N (continental North America + Cuba + parts of oceans)
- Temporal cadence: 1181 SMA steps per hourly scan; scan split into 9 granules (~6.7 min each)
- Each granule: ~131 E/W SMA steps × 2048 N/S slit pixels

---

## Level 2 Clouds (CLDO4): Effective Cloud Fraction and Optical Centroid Pressure

### Purpose
Retrieve two cloud parameters for every TEMPO pixel that are used as inputs to all subsequent trace gas retrievals: the Effective Cloud Fraction (ECF) at 466 nm, and the Optical Centroid Pressure (OCP) from O₂-O₂ absorption at 477 nm. The cloud retrieval must be completed before any trace gas retrieval can begin.

**Reference:** Wang et al. (2025), ATBD for Version 3 TEMPO O₂-O₂ Cloud Product

### Why clouds matter for trace gas retrievals

A thick cloud at mid-troposphere acts as a bright reflective surface that shields the atmosphere below from observation. The sensitivity of a satellite measurement to NO₂ (or any other trace gas) at a given altitude z depends on whether photons at that altitude are able to reach the detector. Below a dense cloud, photons cannot escape, so the measurement has no sensitivity to pollution beneath the cloud. The cloud fraction and cloud altitude together determine the vertical sensitivity profile of every trace gas retrieval.

The cloud impact is quantified through the Independent Pixel Approximation (IPA): each pixel is modeled as a linear combination of a clear-sky sub-pixel and a fully overcast sub-pixel, weighted by the Effective Cloud Fraction. The cloud itself is modeled as a Lambertian (perfectly diffuse) reflector at the cloud-top pressure, with fixed cloud albedo Rc = 0.8.

Total TOA normalized radiance under IPA:

**Im = Ig·(1−f) + Ic·f**

where Ig = clear-sky radiance, Ic = fully overcast radiance, f = effective cloud fraction.

### Ancillary inputs

| Input | Source | Purpose |
|---|---|---|
| L1B radiance (439–488 nm) | TEMPO L1B | Measurement for DOAS fitting |
| L1B solar irradiance | TEMPO L1B | Reference spectrum for DOAS |
| T/P/q profiles | GEOS-CF NRT (within 24 hr) | Temperature correction for O₂-O₂ |
| Surface pressure | GEOS-CF | Atmospheric column depth |
| 2-m wind speed | GEOS-CF | Cox-Munk ocean glint model |
| GLER land | MODIS MCD43C1/MCD43C2 (22-yr BRDF climatology) | Clear-sky radiance modeling |
| GLER ocean | Cox-Munk model | Clear-sky radiance over water |
| Snow/ice fraction | IMS (Interactive Multisensor Snow/Ice Mapping System) | Blend snow-free and snow-covered albedo |
| VLIDORT LUTs | Pre-computed radiative transfer | Modeled radiances for ECF/OCP |

### Processing steps

**Step 1 — On-orbit spectral calibration:**
Before DOAS fitting, fit the solar irradiance spectrum from L1B against the TSIS-1 high-resolution solar reference convolved with a super-Gaussian slit function. Retrieve width (w), shape (k), asymmetry (αw), and wavelength shift for each of the 2048 across-track pixel positions. This ensures accurate wavelength registration and slit shape characterization.

**Step 2 — DOAS spectral fitting (439–488 nm):**
Perform a simultaneous non-linear least-squares fit of the ratio of Earth-view radiance to solar irradiance in the 439–488 nm window, retrieving slant column densities (SCDs) for: O₂-O₂ (477 nm band), NO₂, O₃, H₂O (vapor), liquid water. Also fit: Ring effect (rotational Raman scattering), vibrational Raman scattering, wavelength shift, a scaling polynomial, and a baseline polynomial.

O₂-O₂ is the key absorber for OCP retrieval. Its measured SCD encodes how deep in the atmosphere photons penetrated — fewer photons reach below a cloud, so the O₂-O₂ SCD is reduced proportionally to cloud height.

**Step 3 — Temperature correction of O₂-O₂ SCD:**
O₂-O₂ cross-sections are measured at a laboratory reference temperature of 223K. The actual atmosphere has temperatures from ~280K near the surface to ~220K at the tropopause. A post-fit regression corrects the retrieved O₂-O₂ SCD for the difference between the reference temperature and the atmospheric temperature profile at the observation location, using GEOS-CF T/P profiles.

**Step 4 — Iterative ECF–OCP retrieval:**
ECF and OCP are coupled and must be retrieved iteratively:
- Initialize: ECF₀ = 0, OCP₀ = surface pressure
- Retrieve OCP from O₂-O₂ SCD and the current ECF estimate, using LUT interpolation at 477 nm
- Update ECF from the 466 nm radiance, given the current OCP, using LUT interpolation
- Repeat until convergence: |ΔECF| < 0.005 (absolute) or < 1% (relative), and |ΔOCP| < 1 hPa
- Maximum 5 iterations

Forward radiances for the LUT interpolation are computed from VLIDORT radiative transfer pre-computed on a grid of: SZA, VZA, RAA, surface/cloud LER, surface/cloud pressure.

### Outputs — CLDO4 product

| Variable | Description | Units |
|---|---|---|
| eff_cloud_fraction | Effective Cloud Fraction at 466 nm | unitless [0–1] |
| cloud_pressure | Optical Centroid Pressure from O₂-O₂ | hPa |
| SCD_MainDataQualityFlag | 0=good, 1=suspicious, 2=bad | unitless |
| ProcessingQualityFlag | 16-bit bitwise flag for specific issues | unitless |

### Known issues (Version 3)
ECF shows a positive bias: clear-sky pixels peak near ECF ~0.05 rather than decreasing monotonically from zero. This is attributed to overestimation of absolute radiance in L1B calibration and inaccuracies in the GLER climatology. The bias propagates into all trace gas retrievals.

---

## Level 2 Trace Gases: NO₂ Retrieval

### Purpose
Retrieve tropospheric and stratospheric NO₂ vertical column densities (VCDs) at the native TEMPO pixel resolution from L1B spectral radiances, using the CLDO4 cloud parameters as inputs to the AMF calculation.

**Reference:** Nowlan et al. (2025), ATBD for Version 3 TEMPO Nitrogen Dioxide

### The retrieval chain: three steps

The NO₂ retrieval is conceptually divided into three sequential steps:

```
L1B radiance spectra
        ↓
  [Step 1: Spectral fitting]
  → Slant Column Density (SCD)
        ↓
  [Step 2: AMF calculation]      ← CLDO4 (cloud fraction, cloud pressure)
  → Air Mass Factor (AMF)        ← GEOS-CF (NO₂ profiles, T/P, surface pressure)
        ↓                        ← GLER (surface reflectance)
  [Step 3: Strat-trop separation]  ← runs after full hourly scan complete
  → Tropospheric VCD + Stratospheric VCD
```

---

### Step 1: Slant Column Density Retrieval

**On-orbit spectral calibration (same as CLDO4):**
Fit solar irradiance spectrum against TSIS-1 reference to retrieve super-Gaussian slit function parameters (q, k, aq) and wavelength shift for every across-track position. This is performed once per orbit or scan and applied to all subsequent Earth-view retrievals.

**DOAS spectral fitting window:** 405–465 nm

The algorithm minimizes:

**χ² = [y − F(x,b)]ᵀ Sε⁻¹ [y − F(x,b)]**

where y = measured log-ratio of Earth radiance to solar irradiance; F(x,b) = forward model; Sε = measurement error covariance from photon noise.

**Forward model simultaneous fits:**

| Species | Cross-section source | Temperature |
|---|---|---|
| NO₂ | Vandaele 1998 | 220K |
| O₃ | Serdyuchenko 2014 | 223K |
| O₂-O₂ | Finkenzeller 2022 | 293K |
| H₂O vapor | HITRAN2020 | 283K |
| Liquid H₂O | — | — |
| Ring effect | Chance & Spurr 1997 | — |
| Undersampling | Chance 2005 | — |
| Scaling polynomial | 4th order | — |
| Baseline polynomial | 4th order | — |
| Wavelength shift | — | — |

Bad and hot pixels flagged in L1B are excluded. After an initial fit, any pixel with residuals >3σ is flagged and the fit is repeated without those outliers. The Levenberg-Marquardt nonlinear least-squares solver is used.

**Output of Step 1:** NO₂ SCD [molecules cm⁻²] and SCD uncertainty (SCDuncert).

---

### Step 2: Air Mass Factor (AMF) Calculation

The AMF converts SCD to VCD by accounting for the slant light path geometry and vertical sensitivity:

**VCDtotal = SCD / AMFtotal**

The AMF is evaluated at 440 nm. Three separate AMFs are computed: tropospheric (surface to tropopause), stratospheric (tropopause to TOA), and total (surface to TOA).

**AMF = ∫ W(z) · S(z) · c(z) dz**

where:
- W(z) = scattering weight = altitude-dependent sensitivity of the measurement to absorption
- S(z) = a priori NO₂ profile shape factor = n(z) / ∫n(z)dz [fraction of total column per km]
- c(z) = temperature correction = 1 − 0.00316[T(z)−220K] + 3.39×10⁻⁶[T(z)−220K]²

**Scattering weights W(z)** are pre-computed with VLIDORT and stored in a LUT at 440 nm. LUT nodes: SZA (11 values), VZA (11 values), albedo (8 values), surface pressure (12 values), ozone profile type (22 types: tropical / midlatitude / polar).

**Cloud treatment (IPA):**

W(z) = (1 − fcr)·Wclear(z, α, ps) + fcr·Wcloud(z, αc, pc)

The radiative cloud fraction fcr ≠ fce (ECF from CLDO4). It is weighted by the ratio of cloudy to clear-sky radiance at 440 nm:

fcr = fce · Icloud / [(1−fce)·Iclear + fce·Icloud]

Cloud fraction (fce) and cloud pressure (pc) come from CLDO4. Above the cloud top, W(z) is similar between clear and cloudy. Below the cloud, Wcloud(z) → 0 (no sensitivity to NO₂ below the cloud).

**Surface reflectance inputs:**

| Surface type | GLER model | Source |
|---|---|---|
| Land | MODIS BRDF MCD43C1/MCD43C2 | 22-year climatology, interpolated to day/geometry |
| Open ocean | Cox-Munk + Lambertian | 2-m wind from GEOS-CF |
| Snow/ice pixels | Blend of snow-free + snow-covered | IMS snow/ice fraction |

**Terrain pressure correction:** The GEOS-CF model surface pressure is adjusted to the actual pixel elevation from the GMTED2010 DEM:

ps,obs = ps,model × [Ts / (Ts + Γ(hmodel − hDEM))]^(−g/RΓ)

**A priori NO₂ profiles:** GEOS-CF NRT 5-day forecast, ~25 km horizontal, 72 vertical layers, 0.25°×0.25° output. Fallback: GEOS-CF monthly climatology. Profiles interpolated spatially and temporally to each pixel location and observation time.

**Aerosols:** Not explicitly modeled. Their radiative effects are implicitly captured in the cloud parameters from CLDO4 (CLDO4 retrieves an "effective" cloud fraction that includes aerosol scattering).

**Tropopause:** Taken from GEOS-CF; used to define the troposphere/stratosphere boundary for computing AMFtrop and AMFstrat separately.

---

### Step 3: Stratosphere-Troposphere Separation

Runs once per complete hourly scan (after all 9 granules are processed). This step isolates the tropospheric NO₂ column, which is the primary science product for air quality.

**Why needed:** The total SCD includes both stratospheric (~70% of total column in clean regions) and tropospheric (~30%) contributions. For air quality, only the troposphere matters.

**Algorithm:**

1. Compute initial stratospheric VCD: VCDstrat,init = (SCD − SCDtrop,prior) / AMFstrat
   where SCDtrop,prior = VCDtrop,prior · AMFtrop, and VCDtrop,prior comes from GEOS-CF.

2. Mask polluted pixels: exclude pixels where the prior tropospheric SCD contribution exceeds 0.3×10¹⁵ molecules cm⁻². These pixels have large tropospheric signals that would contaminate the stratospheric reference.

3. Spatial smoothing of unmasked pixels: bin to 0.1°×0.1° grid; apply 15° lon × 10° lat boxcar smooth; remove outliers (>1.5σ) through two passes. Fill missing bins with 30°×20° window.

4. Final smoothing: apply 5°×3° boxcar to the stratospheric VCD field; interpolate to native pixel locations.

5. Compute tropospheric VCD: **VCDtrop = (SCD − VCDstrat · AMFstrat) / AMFtrop**

**Output:** VCDtrop and VCDstrat at native pixel resolution for each granule.

### Outputs — NO₂ L2 product

**Primary product variables:**

| Variable | Description | Units |
|---|---|---|
| product/vertical_column_troposphere | Tropospheric NO₂ VCD | molecules cm⁻² |
| product/vertical_column_stratosphere | Stratospheric NO₂ VCD | molecules cm⁻² |
| product/vertical_column_troposphere_uncertainty | 1-σ random uncertainty on trop. VCD | molecules cm⁻² |
| product/main_data_quality_flag | 0=good, 1=suspicious, 2=bad | unitless |

**Support variables (in support_data/ group):**

| Variable | Description |
|---|---|
| fitted_slant_column | NO₂ SCD from spectral fit |
| fitted_slant_column_uncertainty | SCD 1-σ uncertainty |
| eff_cloud_fraction | Cloud fraction (from CLDO4) |
| amf_cloud_fraction | Radiative cloud fraction for AMF |
| amf_cloud_pressure | Cloud pressure (from CLDO4) |
| amf_troposphere | Tropospheric AMF |
| amf_stratosphere | Stratospheric AMF |
| amf_total | Total AMF |
| amf_diagnostic_flag | 16-bit AMF quality flags |
| scattering_weights | Vertical profile of W(z) |
| gas_profile | A priori NO₂ partial column profile |
| albedo | Surface reflectance |
| surface_pressure | Terrain-corrected surface pressure |
| terrain_height | GMTED2010 terrain elevation |
| tropopause_pressure | Tropopause pressure from GEOS-CF |
| temperature_profile | Atmospheric temperature profile |
| snow_ice_fraction | Fraction of pixel covered by snow/ice |

**Quality flag logic (main_data_quality_flag):**

| Value | Meaning | Criteria |
|---|---|---|
| 0 | Normal (good) | fit_convergence=1 AND |VCDtotal| ≤ 10¹⁹ AND (SCD+2·SCDuncert)≥0 AND AMFgeo≤6 AND AMFtotal≥0.1 |
| 1 | Suspicious | fit failed OR slightly negative SCD OR VCD out of range OR AMFgeo>6 |
| 2 | Bad | fit strongly diverged OR (SCD+3·SCDuncert)<0 OR AMF calculation failed |

**Recommended filtering:** main_data_quality_flag = 0 AND eff_cloud_fraction < 0.2

**Note on total NO₂ column:** Users wanting total NO₂ (for comparison with ground-based Pandora instruments) should use vertical_column_troposphere + vertical_column_stratosphere. The support_data/vertical_column_total is not recommended for most users, as it is strongly influenced by the model prior profile.

### Data URLs
- L2 NO₂ product: https://doi.org/10.5067/IS-40e/TEMPO/NO2_L2.003
- L3 NO₂ (gridded): https://doi.org/10.5067/IS-40e/TEMPO/NO2_L3.003

---

## Level 3 (L3): Gridded Products

### Purpose
Aggregate L2 granule-level retrievals from one complete hourly E/W scan onto a regular spatial grid. L3 products are the standard format for users who want easy-to-use, spatially uniform data for mapping, time series analysis, and model comparisons.

### Processing

Each complete hourly scan (9 granules, ~1 hour of data) is gridded to a regular 0.02°×0.02° lat/lon grid (~2 km × 2 km at mid-latitudes). The gridding uses area-weighted or nearest-neighbor averaging of overlapping L2 pixels. The same quality flags and filtering recommendations apply to L3 as to L2 — L3 products are not pre-filtered.

### Inputs
- All 9 L2 granule files from one complete E/W scan (NO₂, clouds, or other trace gas products)
- Scan timing metadata

### Outputs
- One L3 file per complete hourly scan per trace gas product
- Same variable set as L2 but on the regular 0.02°×0.02° grid
- Includes grid-cell uncertainties and quality flags

### Characteristics
- Temporal resolution: one file per hourly scan (during daylight hours over FOR)
- Spatial resolution: 0.02°×0.02° (~2 km)
- Coverage: continental North America, approximately 10°N–70°N, 170°W–10°W

---

## Other TEMPO L2 Trace Gas Products

The same pipeline framework (DOAS fitting → AMF → VCD) is applied to other atmospheric species using different spectral windows and cross-sections. All trace gas retrievals depend on the CLDO4 cloud product:

| Product | Primary window | Key absorbers fit | Primary science use |
|---|---|---|---|
| NO₂ | 405–465 nm | NO₂, O₃, O₂-O₂, H₂O | Combustion emissions, air quality |
| O₃ (total) | UV | O₃, NO₂, SO₂, BrO | Ozone layer, UV index |
| SO₂ | UV | SO₂, O₃, NO₂, BrO | Volcanic and industrial emissions |
| HCHO | 328–356 nm | HCHO, O₃, NO₂, BrO, OClO | VOC chemistry, biogenic emissions |
| BrO | UV | BrO, O₃, NO₂, HCHO | Halogen chemistry, polar ozone |
| H₂O | VIS (590–740 nm) | H₂O, O₂ | Atmospheric water vapor |

---

## Uncertainty Budget

The total uncertainty in a TEMPO trace gas retrieval has three main contributions:

**1. SCD random uncertainty** (photon noise): determined by the signal-to-noise ratio of the spectral fit. For NO₂ under typical clear-sky conditions, single-pixel VCD precision is below the mission requirement of 1×10¹⁵ molecules cm⁻² (for 4 co-added pixels). Uncertainty increases at high SZA (>70°) due to longer slant paths and reduced solar illumination.

**2. SCD systematic uncertainty** (instrumental and model effects): dominantly from pixel-to-pixel CCD response non-uniformity, causing N/S striping at ±5×10¹⁴ molecules cm⁻² in Version 3. Additional contributions from cross-section temperature selection, slit function characterization errors, and stray light.

**3. VCD systematic uncertainty** (AMF): dominantly from uncertainties in surface reflectance (GLER), cloud parameters (CLDO4 ECF bias), and a priori NO₂ profiles (GEOS-CF). Based on OMI comparisons, AMF structural uncertainty is ~42% over polluted regions and ~31% over unpolluted regions. Over biomass burning plumes with high aerosol loading (not corrected in the AMF), uncertainties can exceed 50–100%.

---

## Data Access and References

**Project homepage:** https://tempo.si.edu (Smithsonian Institution)
**Data portal:** https://asdc.larc.nasa.gov/project/TEMPO (NASA ASDC)

| Product | DOI |
|---|---|
| L1B Radiance | https://dx.doi.org/10.5067/IS-40e/TEMPO/RAD_L1B.003 |
| L1B Irradiance | https://dx.doi.org/10.5067/IS-40e/TEMPO/IRR_L1B.003 |
| L2 Cloud (CLDO4) | https://dx.doi.org/10.5067/IS-40e/TEMPO/CLDO4_L2.003 |
| L2 NO₂ | https://doi.org/10.5067/IS-40e/TEMPO/NO2_L2.003 |
| L3 NO₂ (gridded) | https://doi.org/10.5067/IS-40e/TEMPO/NO2_L3.003 |

**Algorithm references:**
- Wang et al. (2025) — Cloud ATBD: *Earth and Space Science*, 12, e2024EA004132
- Nowlan et al. (2025) — NO₂ ATBD: SAO Science Data Processing Center (SDPC v4.4)
- Zoogman et al. (2017) — Mission overview: *JQSRT*, 186, 17–39
- González Abad et al. (2025) — Status update: EGU25-14296
