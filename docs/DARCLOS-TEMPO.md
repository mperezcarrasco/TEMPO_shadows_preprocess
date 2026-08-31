# Cloud Shadow Detection for TEMPO: Adapting DARCLOS from TROPOMI

**Reference paper:** Trees, V. J. H., Wang, P., & Stammes, P. (2022). DARCLOS: a cloud shadow detection algorithm for TROPOMI. *Atmospheric Measurement Techniques*, 15, 3121–3140. https://doi.org/10.5194/amt-15-3121-2022

**Prepared by:** Analysis based on Trees et al. (2022) and TEMPO Level 2 ATBD documentation

---

## 1. Motivation and Feasibility Assessment

### Why cloud shadows matter for TEMPO

Cloud shadow is a systematic error source in UV/Vis satellite retrievals that is structurally different from cloud contamination. When a cloud casts a shadow on the surface beneath or near it, the shadowed scene receives less direct sunlight. From the satellite's perspective, the shadowed pixel appears darker than its surroundings — not because of cloud interference in the line of sight, but because the *surface itself* is receiving less illumination.

This matters acutely for TEMPO because:

**Effective cloud fraction (ECF) underestimation.** The CLDO4 cloud algorithm uses a scene reflectance model assuming normal surface illumination. In a shadowed pixel, the scene is darker than expected. The IPA model interprets this as a lower cloud fraction, possibly even as clear sky, when the pixel may in fact be shadowed by a nearby cloud. The ECF could be erroneously flagged as near-zero, leading the pixel to pass TEMPO's quality filter (ECF < 0.2).

**Erroneous trace gas columns.** A pixel that passes cloud screening but sits under a cloud shadow will have its air mass factor (AMF) computed under incorrect assumptions. The surface reflectance used in the AMF is drawn from a climatological GLER, not from the actual darker, shadowed scene. The resulting AMF will be biased, and the retrieved tropospheric column (NO₂, HCHO, SO₂, OZONE) will be biased accordingly.

**GEO advantage amplifies the problem.** Because TEMPO observes the same scene hourly, shadows will appear at predictable times and locations relative to clouds. Shadows over urban hotspots — precisely where accurate NO₂ columns matter most — can persist for several granules if the cloud field is stationary.

### Is DARCLOS applicable to TEMPO?

**Yes, with targeted methodological adaptations.** The DARCLOS paper itself states: *"The DARCLOS algorithm can also be applied to other spectrometers with sufficient spatial resolution."* TEMPO's spatial resolution (~2 km × 4.75 km) is comparable to TROPOMI's (~3.5 km × 5.5 km) and fully adequate for detecting cloud shadows cast by resolved clouds. The three-flag DARCLOS framework — geometric screening (PCSF), spectral confirmation (ACSF), and wavelength-dependent UV flagging (SCSF) — maps naturally onto TEMPO's available data products.

The core adaptations required concern: (1) cloud height derivation, since TEMPO retrieves optical centroid pressure rather than physical cloud height; (2) surface reflectance climatology, since TEMPO uses GLER rather than DLER; (3) spectral wavelength selection, since TEMPO's range does not extend into the NIR where DLER typically peaks; and (4) geometry bookkeeping, since TEMPO's fixed geostationary viewing angle greatly simplifies the shadow projection calculation compared to LEO. These are significant engineering tasks but involve no fundamental physical barriers.

---

## 2. Review of the DARCLOS Method

This section summarizes the original DARCLOS algorithm as designed for TROPOMI. The adaptations for TEMPO are described in Section 3.

### 2.1 Three-Flag Architecture

DARCLOS produces three shadow flags per pixel, each with a distinct physical basis:

**PCSF — Potential Cloud Shadow Flag**
A purely geometric flag. It identifies all cloud-free pixels that lie within the geometric shadow of a detected cloud, accounting for the solar zenith and azimuth angles. It is by design conservative: it flags any pixel that *could* be shadowed, without confirming radiometric darkening.

**ACSF — Actual Cloud Shadow Flag**
A spectrally refined flag applied only to PCSF pixels. It confirms actual radiometric darkening by comparing the scene's measured Lambertian-equivalent reflectance (SCNLER) against a directional LER climatology (DLER). A pixel is flagged ACSF when it is measurably darker than expected from the surface alone.

**SCSF — Spectral Cloud Shadow Flag**
A wavelength-resolved flag that reports, for each PCSF pixel, at which individual wavelengths the shadow is radiometrically detectable. This is the most scientifically actionable flag for trace gas retrievals: if a shadow is detectable at 440 nm (the wavelength of the NO₂ DOAS fit window), the corresponding retrieval is directly contaminated.

### 2.2 Geometric Shadow Projection (PCSF)

The effective cloud shadow height, accounting for a safety margin C (set to 0.5 in TROPOMI), is:

```
h = (1 + C) × (h_c − h_sfc)
```

where h_c is the cloud centroid height and h_sfc is the surface height at the shadow location. The horizontal shadow offset from the cloud's nadir point is:

```
x_sh = x_n − h × tan(θ₀) × sin(φ₀)
y_sh = y_n − h × tan(θ₀) × cos(φ₀)
```

Here θ₀ is the solar zenith angle and φ₀ is the solar azimuth angle. Every cloud-free pixel that falls within the triangle defined by the observer (O), the top of the cloud (P), and the shadow tip (Q) is flagged PCSF.

The shadow region is bounded by two angular limits: the angle from the cloud centroid to the observer (defining the near edge of the shadow) and the angle from the cloud centroid to the shadow tip on the surface (defining the far edge). All cloud-free pixels within this angular cone are candidates for shadowing.

### 2.3 Spectral Shadow Confirmation (ACSF)

The scene Lambertian-equivalent reflectance (SCNLER) at each wavelength is computed from the measured top-of-atmosphere radiance:

```
A_scene(λ) = (R_meas(λ) − R⁰(λ)) / (T(λ) + s*(λ) × (R_meas(λ) − R⁰(λ)))
```

where R⁰ is the Rayleigh-only path radiance, T is the two-way atmospheric transmittance, and s* is the spherical albedo. This is the same formulation used in TEMPO's CLDO4 algorithm to compute ECF.

The contrast parameter Γ(λ) quantifies how much darker the scene is relative to the climatological surface reflectance:

```
Γ(λ) = (A_scene(λ) − A_DLER(λ)) / A_DLER(λ) × 100%
```

The ACSF is raised when, at the wavelength where the DLER is maximally reflective (λ_max), the contrast falls below −15%:

```
ACSF raised if: Γ(λ_max) < q = −15%
λ_max = argmax A_DLER(λ)
```

The wavelength λ_max is chosen as the point where the surface reflectance signal is largest and therefore where the contrast between shadowed and unshadowed scene is most detectable.

### 2.4 Wavelength-Dependent Flagging (SCSF)

For every PCSF pixel, the SCSF records at which wavelengths the shadow is detectable (Γ(λ) < −15%). In TROPOMI, this is evaluated at 13 wavelengths spanning 328–494 nm. This allows downstream algorithms to mask retrievals only at the wavelengths that are actually contaminated, rather than discarding the entire pixel.

### 2.5 DLER Climatology

DARCLOS uses a Directional Lambertian-Equivalent Reflectance (DLER) climatology at 0.125° × 0.125° spatial resolution, monthly temporal sampling, and 21 wavelengths spanning 328–2314 nm. The DLER is directional: it accounts for the viewing geometry, making it more accurate than isotropic climatological LER under off-nadir conditions. It is derived from GOME-2 and MODIS observations.

### 2.6 Validated Performance

Against VIIRS true-color imagery as ground truth, DARCLOS achieves F₁ scores of 0.84–0.95 depending on cloud type and scene. False positive rates are low because the ACSF step filters out geometric candidates that are not actually darker. False negatives occur mainly for optically thin clouds that cast faint shadows undetectable at the −15% threshold.

---

## 3. Adaptation of DARCLOS for TEMPO

### 3.1 Cloud Height: Converting OCP to Physical Height

**Problem.** DARCLOS requires physical cloud centroid height (h_c, in meters or km) to compute the geometric shadow offset. TEMPO's CLDO4 product reports Optical Centroid Pressure (OCP, in hPa), not physical height.

**Adaptation.** The conversion from OCP to cloud height must be made using a vertical pressure-to-height profile. The most appropriate approach is to use the GEOS-Chem or MERRA-2 meteorological fields that are already ingested by TEMPO's NO₂ AMF computation. Given a pressure profile p(z) co-located with each granule, the cloud height is obtained by interpolating:

```
h_c = z such that p(z) = OCP
```

A simpler but adequate approximation in the troposphere uses the hypsometric equation assuming a standard atmospheric lapse rate. For the shadow projection calculation, precision in h_c to ~100–200 m is sufficient given the safety margin C = 0.5.

The DARCLOS safety factor C = 0.5 should be retained unchanged. It compensates for uncertainty in both the cloud top height (the true shadow edge) versus the centroid height (what CLDO4 reports), and for subpixel cloud structure not resolved by TEMPO.

**Caveat.** The OCP is a radiative centroid, not the geometric cloud top. For optically thick clouds, the geometric top is higher than the OCP. This means the shadow length could be underestimated by the OCP-based h_c, a bias that is partially but not fully corrected by the C = 0.5 factor. For highly reflective deep convective clouds (ECF ≈ 1), this is most relevant.

### 3.2 Surface Reflectance: Extending GLER to a DLER-Compatible Climatology

**Problem.** DARCLOS uses a DLER climatology: a directional, wavelength-dependent, monthly surface reflectance. TEMPO's CLDO4 and NO₂ algorithms use GLER (a scene-integrated, bidirectional reflectance value derived from MODIS BRDF plus Cox-Munk ocean model at 440/466 nm and limited wavelengths). The TEMPO GLER does not currently provide the full spectral coverage across 293–741 nm needed for DARCLOS.

**Adaptation.** Two options exist, in order of preference:

*Option A — Adopt the existing DLER climatology.* The DLER climatology used in DARCLOS already spans 328–494 nm and covers the full TEMPO UV-VIS range relevant for shadow detection. Since this climatology was generated from GOME-2/MODIS observations at the required wavelengths, it can be used directly with TEMPO. The 0.125° × 0.125° spatial resolution is coarser than TEMPO's pixel grid, but adequate for the statistical shadow screening purpose. A monthly climatology interpolated to observation date and geometry is sufficient.

*Option B — Extend TEMPO GLER to additional wavelengths.* TEMPO's MODIS BRDF-based GLER could in principle be applied at additional wavelengths using spectral extrapolation from the existing MODIS spectral bands. This would provide a more geographically current surface reflectance estimate than the DLER climatology, but requires non-trivial additional computation.

For an initial implementation, Option A is recommended for its simplicity and validated use in DARCLOS.

**Note on directional vs. isotropic.** The DLER is directional and accounts for the fixed geostationary viewing angle — which for TEMPO is particularly well-defined since the viewing zenith angle for each pixel is constant across all observations. The DLER climatology for TEMPO should therefore be generated (or queried) at the fixed TEMPO viewing geometry for each pixel location.

### 3.3 Spectral Wavelength Selection: λ_max in TEMPO's Range

**Problem.** In DARCLOS/TROPOMI, λ_max (the wavelength at which DLER is maximum and thus shadow contrast is most detectable) often falls in the near-infrared (747–772 nm) for vegetated surfaces, which is outside TROPOMI's UV/VIS range. DARCLOS addresses this by using the wavelength of maximum DLER within TROPOMI's spectral coverage for the ACSF criterion. For TEMPO, the spectral range is 293–741 nm (UV detector: 293–494 nm; VIS detector: 538–741 nm).

**Adaptation.** The λ_max for ACSF computation must be selected from within TEMPO's spectral coverage. For different surface types:

- **Vegetation:** DLER rises toward the red-edge at ~700 nm and peaks in the NIR. Within TEMPO's VIS range, λ_max will fall in the 670–741 nm region. This is near but below the red-edge; the contrast signal is present but weaker than in the NIR. The −15% threshold may need to be re-evaluated empirically for vegetated scenes.
- **Bare soil / urban surfaces:** DLER typically increases monotonically across UV-VIS-NIR. λ_max within TEMPO's range will also be in the 700–741 nm region.
- **Ocean:** DLER is low across all wavelengths and decreases toward the red. λ_max for ocean within TEMPO's range may be in the 400–500 nm range where the small but non-negligible glint and scattering contributions peak. Shadow detection over open ocean is less critical for trace gas retrievals.
- **Snow and ice:** DLER is nearly flat across UV-VIS-NIR at high values. λ_max within TEMPO's range is less discriminating; cloud shadow detection over snow is inherently difficult due to high surface reflectance.

For the SCSF, TEMPO's relevant retrieval wavelengths are:
- NO₂ DOAS fit window: 405–465 nm → SCSF evaluation at 416, 425, 440, 463 nm
- HCHO DOAS fit window: ~328–356 nm → SCSF evaluation at 328, 335, 340, 354 nm
- SO₂ / BrO: ~305–360 nm → SCSF at 328, 335, 340 nm
- O₃ (Hartley-Huggins): ~305–340 nm → SCSF at 328, 335, 340 nm

The SCSF provides the key benefit that a shadow flag can be attached to the exact spectral fit window of each product, enabling per-product masking rather than all-or-nothing pixel rejection.

### 3.4 Geostationary Geometry: Fixed Viewing, Moving Sun

**Simplification.** For LEO instruments like TROPOMI, both the viewing angle and the solar angle change with each orbit and overflight. For TEMPO, the viewing zenith angle (VZA) and viewing azimuth angle (VAA) are fixed for each pixel across all observations — TEMPO is parked at 91°W GEO. This eliminates one source of geometric uncertainty.

**Per-granule shadow computation.** The solar zenith angle (SZA) and solar azimuth angle (SAA) do change continuously, because the Earth rotates under the geostationary satellite. Within TEMPO's hourly scan cycle, each of the 9 granules covers a time span of ~6.7 minutes. Across a full scan, the sun moves roughly 1–2° in azimuth and 0.5–1° in zenith. Shadow positions will therefore shift between granules. The DARCLOS geometric calculation must be performed independently for each granule using the per-pixel SZA and SAA at granule observation time.

**Azimuth and zenith geometry.** At low solar elevation (high SZA), shadow lengths are dramatically extended. For TEMPO's observation domain (CONUS and southern Canada/northern Mexico), the SZA ranges from ~20° near local noon in summer to >80° at dawn/dusk edges of the scan. In the high-SZA regime, the geometric shadow footprint expands to cover very large surface areas, and many PCSF flags will be raised that ACSF must then filter. Computational cost scales with the number of PCSF candidates; a practical SZA cutoff (e.g., SZA < 75°) for applying DARCLOS is recommended, consistent with the SZA cut used in TEMPO's own L2 data quality filtering.

### 3.5 Temporal Dynamics: Hourly Cadence

TEMPO's hourly scan is simultaneously an asset and a constraint for cloud shadow detection:

**Asset.** A shadow detected at one observation can be cross-validated against adjacent observations. If a shadow is flagged at 14:00 UTC but not at 13:00 or 15:00 UTC for the same pixel, and the cloud is present at 14:00, the flagging is well-supported. This temporal consistency check is not possible for LEO instruments.

**Constraint.** Cloud shadows move as the sun moves. A shadow flag computed for a granule at 14:05 UTC is not valid for 14:11 UTC (the next granule). Shadow positions must be recomputed for each granule. Additionally, clouds themselves move with wind, so the cloud location used for shadow projection must be the cloud position at the time of the granule, not a temporally averaged position.

### 3.6 Validation Strategy: GOES-East as VIIRS Substitute

In the DARCLOS paper, validation was performed by co-locating TROPOMI shadow flags with VIIRS true-color RGB imagery, which has ~375 m spatial resolution and provides a visual ground truth for shadow presence. TEMPO does not have a co-orbiting high-resolution imager.

**Adaptation.** GOES-East (GOES-16) is the natural validation dataset for TEMPO. GOES-East:
- Is geostationary at 75.2°W, providing near-continuous imagery over TEMPO's domain
- Provides ABI imagery at 0.5–2 km spatial resolution in the visible bands (Band 2 at 0.64 µm at 0.5 km)
- Is time-coincident with every TEMPO granule (GOES-East has 1-min mesoscale and 5-min CONUS scan capability)
- Provides true-color composites that visually display cloud shadows as dark regions on the surface

The validation workflow would match TEMPO shadow flags to GOES-East ABI true-color imagery for coincident scenes, computing precision, recall, and F₁ score as in Trees et al. (2022). GOES-East ABI Band 7 (3.9 µm) provides complementary cloud-top temperature that can help constrain cloud height independently.

---

## 4. Proposed TEMPO-DARCLOS Pipeline

### 4.1 Position in the TEMPO Processing Chain

DARCLOS-TEMPO should be inserted as a **post-L2 Clouds, pre-L2 Trace Gases** step. It requires CLDO4 cloud products as input and produces shadow flags that are then consumed by the L2 NO₂, HCHO, SO₂, and O₃ algorithms.

```
L1B Radiances
     ↓
L2 CLDO4 Cloud Algorithm   →   ECF, OCP per pixel
     ↓
[DARCLOS-TEMPO Shadow Detection]   →   PCSF, ACSF, SCSF flags per pixel
     ↓
L2 Trace Gas Retrievals (NO₂, HCHO, SO₂, O₃)   →   columns with shadow quality flag
     ↓
L3 Gridded Products
```

The shadow flags should be propagated to L3 as ancillary quality metadata, allowing users to optionally filter shadow-contaminated retrievals depending on their application.

### 4.2 Inputs

| Input | Source | Description |
|-------|--------|-------------|
| ECF per pixel | TEMPO L2 CLDO4 | Effective cloud fraction at 466 nm |
| OCP per pixel | TEMPO L2 CLDO4 | Optical centroid pressure (hPa) |
| SZA, SAA per pixel | TEMPO L1B / L2 geolocation | Solar zenith and azimuth angle at pixel center |
| VZA, VAA per pixel | TEMPO L1B / L2 geolocation | Fixed geostationary viewing angles |
| Surface elevation h_sfc | GMTED2010 DEM | Already used in TEMPO NO₂ AMF computation |
| L1B radiances R_meas(λ) | TEMPO L1B | Calibrated top-of-atmosphere radiance spectra |
| Rayleigh path radiance R⁰(λ) | VLIDORT LUT | Computed at DARCLOS wavelengths |
| Atmospheric transmittance T(λ) | VLIDORT LUT | Two-way transmittance for SCNLER computation |
| Spherical albedo s*(λ) | VLIDORT LUT | For SCNLER computation |
| DLER climatology A_DLER(λ) | Trees et al. / adapted | Monthly 0.125° × 0.125°, 21 wavelengths; queried at TEMPO viewing geometry |
| Meteorological pressure profile | MERRA-2 / GEOS-Chem | For OCP → physical height conversion |
| Pixel geolocation (lat, lon) | TEMPO L1B geolocation | Center coordinates and corner coordinates |

**Cloud-free pixel mask.** ECF < 0.05 (or the main_data_quality_flag = 0 threshold from L2 NO₂) defines the set of pixels eligible for PCSF flagging. Cloud pixels themselves are not shadow candidates.

**Cloudy pixel identification.** ECF ≥ 0.2 (the cloud screening threshold used in NO₂ QA filtering) identifies cloudy pixels whose shadow footprint is projected onto neighboring clear pixels.

### 4.3 Processing Steps

**Step 1: OCP to Cloud Height Conversion**

For each granule, for every pixel with ECF ≥ 0.2:
1. Extract co-located MERRA-2 pressure-height profile p(z)
2. Interpolate: h_c = altitude where p(z) = OCP
3. Compute effective shadow height: h = (1 + 0.5) × (h_c − h_sfc)

**Step 2: Geometric Shadow Projection (PCSF)**

For each cloudy pixel:
1. Compute shadow tip coordinates using SZA, SAA at granule observation time:
   - x_sh = x_n − h × tan(SZA) × sin(SAA)
   - y_sh = y_n − h × tan(SZA) × cos(SAA)
2. Define the shadow triangle OPQ (observer → cloud top → shadow tip)
3. Test each cloud-free pixel in the neighborhood: if the pixel center falls within triangle OPQ, raise PCSF = 1

**Step 3: SCNLER Computation at DARCLOS Wavelengths**

For each PCSF-flagged pixel, compute scene LER at evaluation wavelengths using TEMPO L1B radiances:

```
A_scene(λ) = (R_meas(λ) − R⁰(λ)) / (T(λ) + s*(λ) × (R_meas(λ) − R⁰(λ)))
```

Evaluation wavelengths aligned to TEMPO products: 328, 335, 340, 354, 367, 380, 388, 402, 416, 425, 440, 463, 494 nm (UV range) and 550, 600, 670, 700, 740 nm (VIS range, for λ_max determination).

**Step 4: Contrast Computation**

For each PCSF pixel at each wavelength:
```
Γ(λ) = (A_scene(λ) − A_DLER(λ)) / A_DLER(λ) × 100%
```

Determine λ_max = argmax A_DLER(λ) within TEMPO's spectral range (293–741 nm) for each pixel's surface type.

**Step 5: ACSF Determination**

If Γ(λ_max) < −15%: raise ACSF = 1 for that pixel.

**Step 6: SCSF Determination**

For each PCSF pixel, record SCSF(λ) = 1 for every evaluation wavelength where Γ(λ) < −15%.

Specific product-relevant SCSF summary flags:
- SCSF_NO2: any of {416, 425, 440, 463} nm has SCSF = 1
- SCSF_HCHO: any of {328, 335, 340, 354} nm has SCSF = 1
- SCSF_SO2: any of {328, 335, 340} nm has SCSF = 1

### 4.4 Outputs

| Output Variable | Type | Description |
|----------------|------|-------------|
| `pcsf` | uint8, per pixel | 1 if pixel is geometrically in cloud shadow, 0 otherwise |
| `acsf` | uint8, per pixel | 1 if shadow radiometrically confirmed (Γ(λ_max) < −15%), 0 otherwise |
| `scsf` | uint8 array, per pixel, per wavelength | 1 at each wavelength where shadow is radiometrically detectable |
| `scsf_no2` | uint8, per pixel | Summary: shadow detectable in NO₂ DOAS window |
| `scsf_hcho` | uint8, per pixel | Summary: shadow detectable in HCHO DOAS window |
| `scsf_so2` | uint8, per pixel | Summary: shadow detectable in SO₂/BrO window |
| `shadow_contrast` | float32 array, per pixel, per wavelength | Γ(λ) values for quality assessment |
| `cloud_shadow_height` | float32, per cloudy pixel | Effective h = (1+C)(h_c − h_sfc) used in projection (km) |

The `acsf` flag is the recommended primary quality filter for trace gas retrievals: it is specific enough to exclude non-shadow darkening (topographic shading, aerosol plumes) and sensitive enough to catch the majority of actual shadows. The `scsf_*` product-specific flags are recommended for precision applications where per-window contamination assessment is needed.

---

## 5. Required Methodological Changes: Summary

| Aspect | DARCLOS (TROPOMI) | TEMPO Adaptation | Impact |
|--------|------------------|------------------|--------|
| Cloud height | FRESCO physical cloud height | OCP converted via MERRA-2 pressure profile | Moderate: OCP underestimates cloud top; C=0.5 partially corrects |
| Surface reflectance | DLER climatology (21 λ, 0.125°) | Same DLER climatology queried at fixed TEMPO VZA/VAA | Minor: DLER is directional; fixed GEO geometry simplifies query |
| λ_max for ACSF | Can fall in NIR (747–772 nm) | Constrained to ≤741 nm; vegetation λ_max in VIS 670–741 nm | Minor–Moderate: lower reflectance at λ_max; −15% threshold may need recalibration |
| SCSF wavelengths | 328–494 nm (13 wavelengths) | 328–494 nm + 550–740 nm for λ_max; trace gas windows targeted | Minor: extends coverage; directly addresses TEMPO product windows |
| Viewing geometry | Changing (LEO orbit) | Fixed (GEO 91°W) | Simplification: per-pixel VZA/VAA constant; reduces DLER lookup complexity |
| Solar geometry | Fixed per overpass | Changes per granule (Earth rotation) | Moderate: shadow recomputed per granule (~6.7 min intervals) |
| Validation | VIIRS true-color co-location | GOES-East ABI true-color + Band 7 cloud-top temperature | Straightforward: GOES-East is concurrent, high-resolution |
| SZA cutoff | Not specified | Recommend SZA < 75° (consistent with TEMPO L2 QA) | Minor: excludes dawn/dusk edge retrievals |
| Computational domain | Global LEO swath | TEMPO domain (CONUS + adjacent) | Reduction in computational load |

---

## 6. Limitations and Open Questions

**ACSF threshold calibration.** The −15% contrast threshold was tuned empirically for TROPOMI's spectral range, which includes NIR wavelengths where surface contrast between shadowed and unshadowed scenes is largest. For TEMPO, where λ_max is capped at 741 nm, the contrast at λ_max may be systematically reduced for vegetated surfaces. A recalibration of the threshold using GOES-East ground truth is advisable before operational deployment.

**Thin cloud shadows.** DARCLOS has documented difficulty with optically thin clouds (ECF < 0.4) that cast faint shadows. At TEMPO's −15% threshold, thin cloud shadows may not consistently exceed the ACSF detection limit. These shadows, while small in amplitude, still bias HCHO and SO₂ retrievals, which have higher measurement noise and smaller signal-to-noise than NO₂. Whether the threshold should be relaxed for UV products requires dedicated sensitivity analysis.

**Aerosol plume confusion.** Dense aerosol plumes (smoke, dust) can darken the surface-equivalent scene LER in a pattern that mimics cloud shadow: the A_scene is reduced relative to A_DLER. DARCLOS partially mitigates this through the PCSF geometric pre-filter — only PCSF-flagged pixels are assessed by ACSF. However, if an aerosol plume is co-located below or downwind of a cloud, the two effects can superimpose. The TEMPO aerosol product (if available) could be used as an additional discriminator.

**OCP-to-height accuracy.** The accuracy of the OCP-to-height conversion depends on the fidelity of the co-located pressure profile. MERRA-2 profiles have ~0.5–1 km vertical resolution in the troposphere. For shallow, low-lying clouds (marine stratus, fog), the cloud height may be 0.5–1 km above the surface, and errors of similar magnitude in h_c will severely distort the shadow footprint. The safety margin C = 0.5 helps, but a re-evaluation of C for TEMPO's cloud type distribution (which includes more continental convection than TROPOMI's global average) is warranted.

**Sub-pixel cloud structure.** TEMPO's pixels at ~2 km × 4.75 km may contain partially cloudy pixels where the cloud only occupies a fraction of the pixel. The shadow projection uses the cloud pixel's center as the shadow source, which is valid for overcast pixels but introduces spatial error for patchy cloud. ECF thresholding (using only pixels with ECF > 0.5 as shadow sources) may improve shadow localization precision.

**No spectral overlap with TEMPO's UV range below 328 nm.** The DLER climatology begins at 328 nm. TEMPO observes down to 293 nm, covering the SO₂ and O₃ Hartley bands. Shadow flags below 328 nm cannot be generated with the current DLER climatology. An extension of the DLER to shorter UV wavelengths using TOMS/OMI observations would be needed to cover this range. In the interim, SCSF flags at 328 nm can serve as a proxy for shadow impact in the 305–328 nm range.

---

## 7. Scientific Value and Priority

The DARCLOS-TEMPO algorithm addresses a currently unmitigated systematic error source in TEMPO trace gas products. Its priority is highest for:

1. **NO₂ over urban areas.** City centers under afternoon cumulus shadows are precisely where hourly NO₂ monitoring is most valuable for air quality applications. A shadow-contaminated pixel passing the ECF < 0.2 quality filter can produce an erroneously high apparent NO₂ column (darkened scene → lower AMF → inflated column) or erroneously low column (scene interpreted as clear but illumination reduced). Either bias undermines the accuracy of TEMPO's urban air quality products.

2. **HCHO over biogenic sources.** HCHO is emitted by isoprene-emitting vegetation (forests, crops) — exactly the surface types where cloud shadows are geometrically most extended in summer afternoons. Biogenic HCHO retrievals over forests using TEMPO data would particularly benefit from shadow masking.

3. **SO₂ near point sources.** Power plants and industrial facilities may be located in regions with frequent afternoon convection. Shadow flags at SO₂ wavelengths (328–340 nm) would help ensure that apparent plume detections are not shadow artifacts.

4. **Trend analysis and validation campaigns.** For multi-year trend detection and satellite-to-aircraft or satellite-to-ground comparisons, shadow-contaminated pixels introduce random (and potentially systematic, if cloud patterns are seasonally correlated with emission sources) noise in the time series.

---

## 8. References

- Trees, V. J. H., Wang, P., & Stammes, P. (2022). DARCLOS: a cloud shadow detection algorithm for TROPOMI. *Atmospheric Measurement Techniques*, 15, 3121–3140. https://doi.org/10.5194/amt-15-3121-2022

- Wang, P., et al. (2025). TEMPO Cloud ATBD (CLDO4): Effective Cloud Fraction and Optical Centroid Pressure from O₂-O₂ at 477 nm. TEMPO Algorithm Theoretical Basis Document.

- Nowlan, C. R., et al. (2025). TEMPO NO₂ ATBD: Tropospheric NO₂ from DOAS. TEMPO Algorithm Theoretical Basis Document.

- Zoogman, P., et al. (2017). Tropospheric Emissions: Monitoring of Pollution (TEMPO). *Journal of Quantitative Spectroscopy and Radiative Transfer*, 186, 17–39.

- González Abad, G., et al. (2025). TEMPO Formaldehyde ATBD.

- Boersma, K. F., et al. (2018). Improving algorithms and uncertainty estimates for satellite NO₂ retrievals: results from the quality assurance for the essential climate variables (QA4ECV) project. *Atmospheric Measurement Techniques*, 11, 6651–6678.
