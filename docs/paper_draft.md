# DARCLOS-TEMPO: A cloud shadow detection algorithm adapted from TROPOMI to the geostationary TEMPO instrument

*Working draft — vN, June 2026.*

**Authors:** M. Pérez-Carrasco¹, Q. Zhu¹

---

## Abstract

Cloud shadows are a systematic but currently unmitigated error source in
the trace-gas retrievals of the Tropospheric Emissions: Monitoring of
Pollution (TEMPO) mission. A pixel that lies under the shadow of a nearby
cloud is darker than its clear-sky climatology would predict, biasing the
air-mass-factor estimate used to convert slant to vertical columns of NO₂,
HCHO, SO₂, and O₃. We present an adaptation of the DARCLOS cloud-shadow
detection algorithm (Trees et al., 2022) to the geostationary, UV-VIS
spectrometer geometry of TEMPO. Three adaptations are required: (i) physical
cloud heights must be derived from the operational Optical Centroid Pressure
(OCP) product (CLDO4 V04, Wang et al. 2025), since TEMPO L1B does not
populate cloud-top height; (ii) the directional Lambertian-equivalent
reflectance (DLER) climatology used by DARCLOS to confirm shadow darkening
is unavailable for TEMPO, but the CLDO4 effective cloud fraction (ECF)
inversion already encodes the same darker-than-GLER signal and can be used
as a single-wavelength surrogate; and (iii) viewing and solar azimuth angles
must be sourced from the L1B band group because the V03/V04 L2 geolocation
azimuth fields are largely fill-valued. We implement the algorithm in a
fully vectorized form using ECEF-coordinate k-d trees for nearest-pixel
lookup, with two operational modes — per-granule and per-scan (merged at
the L1B/L2 array level before the algorithm runs). The pipeline produces
GeoTIFF and shapefile outputs ready for downstream consumption. Visual
validation against TEMPO RGB composites on multiple full-day scans
(September 2025) shows that the algorithm correctly identifies the
position, direction, and extent of cloud shadows for resolved cumulus and
stratus, with documented failure modes over open ocean, snow, and dense
aerosol plumes. We discuss the limitations of the single-wavelength
radiometric surrogate, the Bresenham-line projection of the cloud umbra,
and the bounding-box affine georeferencing inherent in the swath-grid
output, and identify a prioritized roadmap for quantitative validation
against GOES-East ABI imagery, polygonal umbra projection, and
multi-wavelength refinement using SceneLER440/SceneLER466.

**Keywords:** TEMPO, DARCLOS, cloud shadow, atmospheric chemistry,
geostationary remote sensing, NO₂, formaldehyde, ozone monitoring.

---

## 1. Introduction

The Tropospheric Emissions: Monitoring of Pollution (TEMPO) mission
(Zoogman et al., 2017), launched in April 2023 and operational since the
following August, is the first geostationary UV-VIS atmospheric composition
spectrometer over North America. From 91°W geostationary orbit, TEMPO
provides hourly observations of NO₂, HCHO, SO₂, O₃, glyoxal, water vapour,
and aerosol indices at a sub-urban spatial resolution of approximately
2.0 km (north-south) × 4.75 km (east-west) at field centre. The hourly
cadence is unprecedented for trace-gas measurements at this resolution and
is intended to capture the diurnal cycle of emissions and chemistry over
the United States, southern Canada, Mexico, and the Greater Antilles.

A key strength of TEMPO — repeated observation of the same scene throughout
the day — is also a source of compounded uncertainty when systematic errors
correlate with the diurnal evolution of clouds. Among such errors, cloud
shadows are particularly problematic. A shadow is not a cloud in the line
of sight; it is a region of the surface receiving reduced direct solar
illumination because an adjacent cloud blocks the sun. From the satellite's
perspective the shadowed pixel is anomalously dark — not because of
in-atmosphere extinction, but because the surface itself is darker than the
algorithm's climatology assumes. Through the Independent Pixel
Approximation (IPA) framework used in the CLDO4 cloud product (Vasilkov
et al. 2018; Wang et al. 2025), the darkening is partly absorbed into the
retrieved Effective Cloud Fraction (ECF), driving it toward zero (or
slightly negative, pre-clipping). A shadow-contaminated pixel can therefore
pass the standard NO₂ quality filter of ECF < 0.2 while being radiometrically
biased. The bias then propagates into the air-mass-factor (AMF) calculation,
which assumes the climatological GLER as the surface reflectance, and
ultimately into the retrieved trace-gas column.

The problem is not unique to TEMPO. For TROPOMI (LEO, 7×3.5 km² at nadir),
Trees, Wang, and Stammes (2022) developed the **DARCLOS** (Detection of
Cloud-Affected Pixels by ReCognition Of Shadows) algorithm, which has been
validated against VIIRS true-colour imagery with F1 scores of 0.84–0.95
depending on cloud type and surface. DARCLOS produces three per-pixel
flags: PCSF (Potential Cloud Shadow Flag — pure geometry), ACSF (Actual
Cloud Shadow Flag — radiometric confirmation), and SCSF (Spectral Cloud
Shadow Flag — wavelength-resolved confirmation for each trace-gas DOAS
window). The DARCLOS paper itself notes that the algorithm "can also be
applied to other spectrometers with sufficient spatial resolution".

In this work, we adapt DARCLOS to TEMPO. Three structural differences
between TROPOMI and TEMPO drive the adaptation:

1. **Cloud height.** TROPOMI uses FRESCO-S physical cloud-top height
   directly; TEMPO's CLDO4 product reports Optical Centroid Pressure
   (OCP) but the L1B cloud_top_height field is largely fill-valued.
2. **Surface reflectance.** DARCLOS confirms shadows by comparing
   TOA-derived Lambertian-equivalent reflectance (SCNLER) against a
   directional Lambertian-equivalent reflectance (DLER) climatology
   at 13 wavelengths (328–494 nm). TEMPO's operational surface reflectance
   is the Geometry-dependent LER (GLER), and it is only provided at 440
   and 466 nm in CLDO4 V04.
3. **Geometry.** TEMPO is geostationary, so viewing geometry is fixed per
   pixel for the lifetime of the mission, but solar geometry changes
   continuously across the day.

Section 2 reviews the DARCLOS three-flag framework and the relevant elements
of the CLDO4 algorithm. Section 3 details the adaptation choices, including
the OCP-to-height hypsometric conversion, the use of the CLDO4 ECF
retrieval as a single-wavelength ACSF surrogate, the vectorized geometric
projection, and the two operational modes of the implementation (per-granule
and per-scan, the latter merging L1B/L2 arrays before the algorithm runs).
Section 4 presents sample results validated by visual inspection against
TEMPO RGB composites for September 2025 scans. Section 5 discusses
theoretical and implementation limitations. Section 6 outlines next steps,
focusing on quantitative GOES-East ABI validation and the recovery of the
polygonal umbra footprint.

---

## 2. Background

### 2.1 The geometry of a cloud shadow

A cloud at height $h_c$ above the surface, illuminated by the sun at solar
zenith angle $\theta_0$ and solar azimuth angle $\phi_0$, casts a shadow
whose horizontal displacement from the cloud's nadir point on the surface
is

$$
\Delta x_{\rm sh} = -h \tan\theta_0 \sin\phi_0, \qquad
\Delta y_{\rm sh} = -h \tan\theta_0 \cos\phi_0,
$$

where $h$ is the effective cloud height above the local surface
$h_{\rm sfc}$. For a satellite viewing at zenith angle $\theta$ and azimuth
$\phi$, the cloud appears parallax-displaced from its nadir projection by

$$
\Delta x_n = h \tan\theta \sin\phi, \qquad
\Delta y_n = h \tan\theta \cos\phi.
$$

The shadow ground location relative to the observed pixel centre is the
sum of these two displacements:

$$
\Delta x = h \big(\tan\theta \sin\phi - \tan\theta_0 \sin\phi_0\big),
\quad
\Delta y = h \big(\tan\theta \cos\phi - \tan\theta_0 \cos\phi_0\big).
$$

These are DARCLOS Eqs. 2–5. The conversion to geodetic offsets uses the
local Earth radii of curvature $M, N$ at the cloud latitude $\phi_c$:

$$
\Delta\phi = \frac{\Delta y}{M + h_{\rm sfc}}, \quad
\Delta\lambda = \frac{\Delta x}{(N + h_{\rm sfc}) \cos\phi_c}.
$$

In practice, $M \approx N \approx 6{,}378{,}137$ m and the cosine correction
dominates.

### 2.2 The DARCLOS three-flag framework

DARCLOS introduces a *safety factor* $C = 0.5$ that enlarges the effective
height used in the projection,

$$
h = (1+C)(h_c - h_{\rm sfc}), \tag{DARCLOS Eq.~1}
$$

to absorb the uncertainty between the cloud centroid (what the retrieval
reports) and the true geometric cloud top (what casts the umbra), as well
as sub-pixel cloud structure. With the projected shadow on the surface,
the **PCSF** is set to 1 for every cloud-free pixel that lies inside the
triangle OPQ defined by the observer O, the cloud-top point P, and the
shadow-tip point Q.

The **ACSF** refines PCSF radiometrically. DARCLOS computes the Scene
Normalized Lambertian-Equivalent Reflectance (SCNLER) directly from the
measured TOA radiance via a Rayleigh-correction lookup table,

$$
A_{\rm scene}(\lambda) =
\frac{R^{\rm meas}(\lambda) - R^0(\lambda)}
     {T(\lambda) + s^*(\lambda) T^{\rm meas}(\lambda) - R^0(\lambda)},
$$

and compares it with the DLER climatology of Tilstra et al. (2017, 2024).
The contrast

$$
\Gamma(\lambda) = \frac{A_{\rm scene}(\lambda) - A_{\rm DLER}(\lambda)}
                       {A_{\rm DLER}(\lambda)} \times 100\%
$$

is evaluated at $\lambda_{\max} = \arg\max_\lambda A_{\rm DLER}(\lambda)$,
where shadow detectability is highest. The ACSF is raised when
$\Gamma(\lambda_{\max}) < q = -15\%$. The **SCSF** repeats this check at
13 individual wavelengths (328–494 nm) to produce per-window flags for
downstream NO₂, HCHO, SO₂, and O₃ retrievals.

### 2.3 The TEMPO CLDO4 cloud product

The TEMPO O₂-O₂ cloud product CLDO4 (Wang et al., 2025) inherits its
forward model from the OMI O₂-O₂ algorithm (Vasilkov et al. 2018) and is
based on the Independent Pixel Approximation: the modelled TOA normalized
radiance is

$$
I_m = I_g(1 - f) + I_c f, \tag{CLDO4 Eq.~1}
$$

where $I_g$ is the clear-sky TOA radiance over a Lambertian surface of
reflectance equal to the GLER and $I_c$ is the cloudy TOA radiance over a
Lambertian cloud of fixed reflectance $R_c = 0.8$ at scene pressure. The
algorithm retrieves the effective cloud fraction $f$ (ECF) at 466 nm from
$I_m$, and the Optical Centroid Pressure (OCP) from the O₂-O₂ Slant Column
Density at 477 nm. Crucially, the ECF inversion uses GLER as its
*clear-sky surface reference* — so a pixel that is geometrically clear but
radiometrically darkened by a cloud shadow has $I_m < I_g$, and the
retrieval drives ECF toward 0 (and, before clipping, toward negative
values). This will become the basis of our ACSF surrogate (§ 3.3).

CLDO4 also exposes two scene-level diagnostic fields that are central to
DARCLOS-style work but not used in operational retrievals: SceneLER466
and SceneLER440. SceneLER466 is the Lambertian-equivalent reflectance that
would reproduce $I_m$ under the assumption of full cloud cover; for a
clear, unshadowed pixel it should equal GLER466 (this is the paper's
internal consistency check). For a shadowed pixel it falls below GLER466.

---

## 3. Methodology

### 3.1 Overview

Our adaptation of DARCLOS-TEMPO retains the two-stage geometric-then-
radiometric structure of the original algorithm but replaces three
components, in each case minimizing the dependencies on data products not
currently available for TEMPO. Figure 1 shows the pipeline.

> *Figure 1.* (placeholder) Pipeline schematic. Inputs: L1B (RGB, angles,
> `cloud_top_height`) and CLDO4 L2 (`cloud_fraction`, `cloud_pressure`,
> `surface_pressure`, `terrain_height`, geolocation). Steps: (a) cloud
> height, (b) vectorized DARCLOS Eqs. 2–7 projection, (c) k-d-tree
> nearest-pixel mapping, (d) Bresenham line rasterization to produce PCSF,
> (e) ACSF refinement via the ECF<0.05 surrogate. Outputs: per-granule or
> per-scan GeoTIFF + three shapefiles.

The three adapted components are:

1. **Cloud height** — replace FRESCO physical cloud-top height with a
   hypsometric conversion of CLDO4 OCP, capped at 16 km and augmented by
   the DARCLOS safety factor $C = 0.5$ (§ 3.2).
2. **Radiometric refinement** — replace the SCNLER-vs-DLER contrast at
   13 wavelengths with a single-wavelength surrogate that reads off the
   CLDO4 ECF inversion (§ 3.3). The physical basis is that the CLDO4 ECF
   retrieval already inverts $I_{\rm meas}$ against GLER through Eq. CLDO4-1,
   so a low ECF at a geometrically predicted shadow location encodes the
   same "darker than the GLER climatology" signal that the DARCLOS
   $\Gamma < -15\%$ criterion is designed to detect.
3. **Geometric projection** — vectorize DARCLOS Eqs. 2–7 over all
   cloud-source pixels in a single NumPy call, replace the per-source
   `argmin` over the full granule with a single batched `cKDTree.query` in
   ECEF coordinates, and rasterize the cloud-to-shadow line using
   Bresenham's algorithm (§ 3.5). The projection uses solar and viewing
   angles from the L1B band group (§ 3.4) because the L2 azimuth fields
   are largely fill-valued in V03 and V04.

### 3.2 Cloud height from Optical Centroid Pressure

The hypsometric equation relates pressure and altitude in an isothermal
atmosphere through a constant scale height $H_{\rm scale}$,

$$
h_{\rm above\,terrain} = H_{\rm scale}\, \ln\!\left(\frac{p_{\rm sfc}}{p_{\rm cloud}}\right),
$$

which we use with $H_{\rm scale} = 8500$ m. The cloud altitude above sea
level is $h_c^{\rm ASL} = h_{\rm above\,terrain} + h_{\rm terrain}$, capped at
$h_{\rm cap} = 16$ km to bound deep-convection cases where OCP can be very
low. The effective shadow-projection height is then

$$
h = (1 + C)\,(h_c^{\rm ASL} - h_{\rm terrain}), \quad C = 0.5,
$$

following the DARCLOS safety-factor convention.

We adopt a two-branch priority. Where the L1B `cloud_top_height` field is
finite and above the local terrain, we use it directly (subject to the same
$h_{\rm cap}$ ceiling and safety factor). Where it is fill-valued — which is
the great majority of TEMPO V03/V04 pixels — we fall back to the
hypsometric formula. Where the cloud is retrieved at or below the surface
($p_{\rm cloud} \geq p_{\rm sfc}$, characteristic of marine stratus and fog
in CLDO4), we set $h = 0$, which collapses the projection and casts no
shadow. Pixels for which neither branch yields a physical height are
counted and reported; if the dropped fraction exceeds a configurable
guard $f_{\rm drop\,max}$ for the granule or scan, processing fails. In
practice this threshold is most often hit by snow-covered or very-high-SZA
scans, where OCP retrieval skips a large fraction of cloud pixels (CLDO4
processing_quality_flag bit 13).

A constant scale height is correct to ≈10 % in the troposphere
(Wallace and Hobbs, 2006). Because the DARCLOS safety factor enlarges the
projection by 50 %, errors at this scale are absorbed; a true MERRA-2-based
profile would refine the height bias at high latitudes and in winter but
is not required for first-order shadow detection.

### 3.3 ECF as a single-wavelength ACSF surrogate

Let $A^{\rm scene}(466 nm)$ be the SceneLER and $A^{\rm GLER}(466 nm)$ be the
GLER at the same pixel. The DARCLOS $\Gamma$ contrast at 466 nm is

$$
\Gamma(466 nm) = \frac{A^{\rm scene}(466 nm) - A^{\rm GLER}(466 nm)}
                       {A^{\rm GLER}(466 nm)}.
$$

For a clear, unshadowed pixel, the CLDO4 self-consistency requires
$A^{\rm scene} \approx A^{\rm GLER}$ (Wang et al. 2025), giving
$\Gamma \approx 0$. For a clear, shadowed pixel, $A^{\rm scene} < A^{\rm GLER}$
and $\Gamma < 0$. In a clear scene, the CLDO4 ECF retrieval inverting
Eq. CLDO4-1 with $I_m < I_g$ produces $f \to 0$ before clipping (and
slightly negative values pre-clipping in V03).

We therefore use the operational ECF directly as a surrogate for the DARCLOS
$\Gamma(\lambda_{\max})$ criterion:

$$
\mathrm{ACSF}(\mathbf{x}) \;=\;
\mathrm{PCSF}(\mathbf{x})
\;\wedge\;
\mathrm{ECF}(\mathbf{x}) < \tau_{\rm shadow},
$$

with $\tau_{\rm shadow} = 0.05$ in our default configuration. Two practical
consequences follow. First, this surrogate operates at one wavelength
(466 nm) only; the wavelength-resolved SCSF is not produced. Second, it
inherits the $\sim 0.05$–$0.10$ positive ECF bias documented for V03
(Wang et al. 2025) — in V03, clear-sky pixels typically have ECF ≈ 0.05,
not 0. V04 reduces this bias substantially, making $\tau = 0.05$ a more
realistic discriminator for V04 than for V03. Cloud-source pixels are
identified by ECF $\geq \tau_{\rm cloud} = 0.30$, which is the threshold
recommended by the TEMPO cloud team for treating a pixel as a coherent
shadow caster.

### 3.4 Source of geometric angles

The DARCLOS projection requires four angles per pixel: solar zenith,
solar azimuth, viewing zenith, viewing azimuth. The TEMPO L2 CLDO4
`geolocation` group nominally contains all four, but for the V03 and V04
data examined here, the viewing azimuth field is *entirely fill-valued*
and the solar azimuth field is ~94 % fill-valued in the affected granules.
A literal use of these values produces a NaN-propagated projection.

We instead read all four angles from the L1B `band_290_490_nm` group,
where they are fully populated. The L1B angles share the per-pixel
identifier with L2 geolocation, so no resampling or coordinate
transformation is needed. This choice is mentioned here because earlier
iterations of the algorithm — which used the L2 azimuth fields directly —
produced visually-plausible but geometrically-incorrect shadow flags whose
projection had no clear directionality.

### 3.5 Vectorized projection, ECEF k-d tree, and Bresenham rasterization

For each cloud-source pixel $\mathbf{x}_k$ in the merged source mask, the
projection equations of § 2.1 produce a target shadow location
$\mathbf{y}_k = (\phi_k^{\rm sh}, \lambda_k^{\rm sh})$. The original DARCLOS
implementation iterates the projection per pixel; we vectorize it with a
single NumPy call over the entire source-pixel array, since each pixel's
projection depends only on its own (lat, lon, height, four angles).

Mapping the projected $(\phi^{\rm sh}, \lambda^{\rm sh})$ back to a grid
index requires a nearest-pixel lookup. A naïve `argmin` over the full
granule grid is $O(N M)$ where $N$ is the number of source pixels and $M$
is the grid size — prohibitive at scan scale ($N \approx 10^5$,
$M \approx 3 \times 10^6$). We instead build a `scipy.spatial.cKDTree` over
the ECEF coordinates of the grid's valid lat/lon pixels and query all
shadow locations in a single batched call (effectively $O(N \log M)$).
The ECEF coordinates avoid the cos(lat) Euclidean-distance bias of a
naïve $(\phi, \lambda)$ distance metric.

Finally, the shadow umbra is rasterized as a Bresenham line from the
cloud-source pixel to the projected shadow location (§ 5.2 discusses the
implications). All non-cloud pixels on the line are added to PCSF. The
ACSF refinement is then a simple boolean AND with the ECF threshold mask.

### 3.6 Operational modes: per-granule and per-scan

We implement two pipeline drivers. **`run_day.py`** processes each TEMPO
granule (a ~6.7-minute slice of one scan) independently and writes one
GeoTIFF + three shapefiles per granule. This is the natural mode for
quick visualization and for granule-level QA. **`run_scan.py`** groups
all granules belonging to one scan (typically 9–11 granules covering a
full east-west pass) and concatenates the L1B and L2 arrays along the
mirror_step axis *before* the DARCLOS algorithm runs. The merged scan is
then processed as a single grid.

The scan-level mode has two advantages over post-hoc mosaicking of
per-granule outputs. First, cloud shadows that physically fall across
granule boundaries are detected correctly — the per-granule mode cannot
project a shadow from a cloud in granule $n$ onto a candidate pixel in
granule $n+1$. Second, the height-validity guard $f_{\rm drop\,max}$ is
averaged across the scan; a single granule with many invalid OCP
retrievals no longer fails the entire pass. The trade-off is that the
single bounding-box affine used to georeference the GeoTIFF spans a
larger area, propagating slightly more swath-grid distortion at the
edges.

### 3.7 Implementation and software architecture

The pipeline is written in Python 3 using NumPy, SciPy, rasterio, fiona,
and h5py. We use h5py rather than `netCDF4.Dataset` for L1B and L2 file
access because the latter triggers HDF5 file-locking errors on some
shared-storage configurations. Shapefiles are written directly via fiona
to avoid the NumPy 2.0 incompatibility in `GeoDataFrame.to_file`.

The code base separates the algorithm (`shadows.py` — pure NumPy/SciPy,
no I/O) from the I/O helpers (`io_utils.py`) and the two CLI drivers
(`run_day.py`, `run_scan.py`). All algorithm parameters — the safety
factor $C$, the cloud and shadow ECF thresholds, the scale height, the
maximum drop fraction — are exposed as YAML config keys with documented
defaults traceable to the original DARCLOS paper or the CLDO4 ATBD.
Source code, configs, and the methodology technical report
(`docs/methodology.md`) are available on the project repository.

---

## 4. Results

### 4.1 Data

We processed all available TEMPO L1B (V04) and CLDO4 L2 (V04) granules for
two days of September 2025 (17 and 18). Each day contains 14–15 scans of
9–11 granules each, for a total of approximately 250 granules per day
covering CONUS, southern Canada, and northern Mexico. Granules with
fully-fill viewing azimuths in the L1B band group were excluded; this
affected only a handful of granules near scan-edge terminator conditions.

### 4.2 Sample results — per-granule mode

> *Figure 2.* (placeholder) Per-granule output, S004G05 of 2025-09-18, a
> mid-morning granule covering the central United States. (a) TEMPO RGB
> composite (gamma-corrected). (b) CLDO4 ECF ≥ 0.30 mask. (c) PCSF mask
> (orange). (d) ACSF mask (red). Note the projected shadow direction
> consistent with the morning sun azimuth (sun is in the south-east, so
> shadows extend toward the north-west).

> *Figure 3.* (placeholder) Per-granule output, S008G04 of 2025-09-18,
> an afternoon granule with a frontal cumulus band over the Great Plains.
> Shadow polygons follow the cloud band on the sun-opposite side.

Across the September 2025 corpus, ACSF flags accounted for typically
4–10 % of cloud-source pixels and 0.5–2 % of all granule pixels. The PCSF
mask is roughly 3–5× larger than ACSF, reflecting the conservative nature
of the geometric pre-filter — PCSF flags all pixels along the projection
line, of which only the truly darkened ones survive the ACSF refinement.

### 4.3 Sample results — per-scan mode

> *Figure 4.* (placeholder) Per-scan output for scan S004 of 2025-09-18,
> covering most of CONUS. (a) Merged RGB mosaic from 11 granules. (b)
> Cloud polygons. (c) Potential shadows. (d) Actual shadows. The
> per-scan mode resolves shadow polygons that cross granule boundaries
> (visible as continuous polygons in panel d that would have been split
> by the per-granule mode).

Compared with the per-granule mosaic of the same scan, the per-scan
output shows (i) consistent pixel size across the entire mosaic — the
per-granule mosaic resamples each granule's affine to a common grid, with
visible seams at granule boundaries; (ii) shadow polygons that extend
across former granule edges where the physical umbra crosses the seam;
and (iii) no scan-level failure due to per-granule OCP-retrieval issues —
even on the snow-affected scan S001 of 2025-09-18 (Manitoba/Ontario
coverage, ~14 % invalid OCP), the scan-level pipeline completes
successfully, with the affected pixels excluded only from shadow casting.

### 4.4 Visual validation

We performed visual validation against the RGB composite for ten randomly
selected granules from 2025-09-17 and ten from 2025-09-18, covering scan
positions S002–S012. For each granule we inspected three properties:

1. **Direction.** Do the ACSF polygons extend away from the casting cloud
   on the side opposite the sun (consistent with morning shadows pointing
   west of north, afternoon shadows pointing east of north)?
2. **Extent.** Are shadow polygons of plausible length given the cloud
   height implied by OCP and the solar zenith angle?
3. **Pairing.** For each non-trivial cloud band in the RGB, does the
   algorithm produce an associated ACSF polygon on the sun-opposite side?

For 18 of 20 inspected granules all three criteria were met. The two
exceptions were granules over open ocean (Gulf of Mexico and Atlantic
Florida coast) where the ACSF over water did not correspond to visible
shadow darkening — a documented false-positive failure mode (§ 5.1).

---

## 5. Limitations

### 5.1 Theoretical / algorithmic limitations

**Open-water and intrinsically dark surfaces.** GLER over open ocean is
typically 0.03–0.05, so the ECF retrieval near coasts and offshore
naturally falls below the $\tau_{\rm shadow} = 0.05$ surrogate threshold
without any shadow being present. Whenever the geometric PCSF projection
happens to cross open water, the ACSF surrogate fires. This is the single
biggest precision risk of the current algorithm and is the primary cause
of the visual-validation failures noted in § 4.4.

**Bright surfaces — snow, ice, deserts.** Conversely, over surfaces with
GLER466 > 0.5 even a real shadow does not depress ECF below 0.05.
Shadow detection over bright surfaces is genuinely difficult and is not
attempted by the surrogate. DARCLOS proper has the same limitation, but
the multi-wavelength SCSF check can recover some detections by inspecting
shorter wavelengths where the contrast is larger.

**OCP-based height bias for deep convection.** OCP is a radiative
centroid, not a geometric top. For optically thick clouds (deep
convection, thunderstorms), the geometric top can be several kilometres
above OCP. Our projection therefore underestimates shadow length for
these clouds. The safety factor $C = 0.5$ partially absorbs this but
does not eliminate it. A height correction tied to cloud optical
thickness would be ideal but is beyond the scope of the operational
CLDO4 product.

**No SZA cutoff.** The algorithm runs at any SZA. At very high SZA (above
≈80°) the shadow projection becomes geometrically unstable and casts
extremely long shadows that often fall outside the granule footprint or
on the night side of the terminator. The TEMPO L2 QA convention is
SZA < 75°; applying that cutoff is in our future-work list.

**Single-wavelength radiometric check.** The DARCLOS SCSF concept —
multi-wavelength shadow flagging — would let downstream NO₂, HCHO, SO₂
retrievals filter on a per-window basis. Our surrogate operates at 466 nm
only. Aerosol-vs-shadow discrimination, which DARCLOS achieves by
comparing the spectral slope of $\Gamma$ across wavelengths (aerosol
darkens shorter wavelengths more), is not available.

**Line vs polygon umbra projection.** We project the cloud's shadow as
a Bresenham line from the source pixel centre to the projected shadow
tip, rather than the full umbra quadrilateral defined by the four pixel
corners as in DARCLOS. The line correctly captures shadow length but
understates width — real umbras are 1–2 TEMPO pixels wide. We
deliberately chose this simpler projection after an earlier polygon
implementation produced sparser and more-fragmented ACSF masks in
empirical testing; the underlying issue was that single-pixel polygons
combined with the strict $\tau_{\rm shadow}$ filter dropped too many
candidate pixels. A revised polygon implementation with cluster-level
union before rasterization is the natural next step.

**Hypsometric height with constant scale height.** Using $H_{\rm scale} =
8500$ m fixed produces approximately 10 % height errors in tropical
versus polar tropopauses. A co-located MERRA-2 pressure-altitude profile
would close this gap; the relevant pipeline component is not yet
implemented.

**Aliased smoke and dust.** Wildfire smoke and Saharan dust can be
retrieved as ECF $\geq 0.5$ by CLDO4 in extreme events (Wang et al. 2025,
§ 3.1). When such a "cloud" is in fact an aerosol plume, our algorithm
will project a "shadow" that is, in reality, the plume's own
contribution to scene darkening superimposed on its location. The
algorithm cannot distinguish smoke from cloud.

### 5.2 Implementation limitations

**No quantitative validation.** Visual inspection against the TEMPO RGB
composite is necessary but not sufficient evidence for operational use.
The recommended quantitative validation reference for TEMPO is GOES-East
ABI true-colour imagery, which is geostationary, time-coincident, and
spatially higher-resolution (Band 2 at 0.5 km). A GOES-East collocation
pipeline is in development.

**Azimuth convention assumption.** The projection assumes the TEMPO L1B
solar and viewing azimuth fields follow the geographic convention (from
North, clockwise, sun direction). Sign errors in the azimuth would
project shadows in the wrong direction but, because of the Bresenham
line plus radiometric AND, still produce visually-plausible outputs.
We have visually verified that projected shadows are consistent with the
sun direction in RGB composites (§ 4.4), but a synthetic single-cumulus
ground truth test has not yet been performed.

**Bounding-box GeoTIFF georeferencing.** TEMPO's swath is curvilinear in
lat/lon. We georeference the GeoTIFF via
`rasterio.transform.from_bounds`, which assumes a regular lat/lon grid
and produces 1–2-pixel-scale geometric distortion at scan edges. For
pixel-accurate georeferencing, GCP-based warping using the granule's
`latitude_bounds`/`longitude_bounds` corners would be required. We
report the algorithm's masks as shapefiles rather than rasterized labels
in part for this reason — vector polygons preserve the precise pixel
centre coordinates regardless of the raster transform.

**Always-overwrite policy.** Each run unconditionally overwrites any
existing outputs in the day or scan output directory. This was a
deliberate choice to make algorithm changes easy to validate; for
large-scale backfills, callers must implement resume logic externally.

**Tied source / class thresholds.** A single $\tau_{\rm cloud} = 0.30$
defines both "this pixel casts a shadow" and "this pixel is a cloud in
the output mask". Decoupling them (e.g. cast at 0.20, classify at 0.30)
would let the algorithm detect shadows from thin cumulus without
inflating the cloud label exposed to downstream consumers.

**Bresenham loop remains scalar.** Geometry, height, projection, and
nearest-pixel lookup are vectorized, but the Bresenham line drawing
is a per-source-pixel Python loop. For $\sim 10^5$ source pixels per
granule this is acceptable (a few seconds), but it is the next
optimization target if the pipeline is run on a long-term TEMPO archive.

---

## 6. Conclusions and future work

We have presented DARCLOS-TEMPO, an adaptation of the DARCLOS cloud
shadow detection algorithm (Trees et al., 2022) to the geostationary UV-VIS
TEMPO instrument. The adaptation retains the two-stage
geometric-then-radiometric structure of the original method while
replacing three components to align with TEMPO's available data products:
(i) cloud height is derived from CLDO4 Optical Centroid Pressure through
a hypsometric conversion with the DARCLOS safety factor preserved; (ii)
the multi-wavelength SCNLER/DLER contrast is replaced by a
single-wavelength surrogate that uses the operational CLDO4 ECF
retrieval, which already encodes the DARCLOS "darker than the GLER
climatology" signal through its MLER inversion; and (iii) the projection
geometry is vectorized over all cloud-source pixels and accelerated with
a batched ECEF k-d-tree nearest-pixel lookup.

The pipeline is implemented in two operational modes — per-granule and
per-scan (with L1B/L2 array concatenation before the algorithm runs) —
and produces georeferenced GeoTIFF and shapefile outputs ready for use
in trace-gas retrieval filtering and labelled-data generation for
machine-learning approaches. Visual inspection of two days of CONUS
coverage (September 17–18, 2025) shows that the algorithm correctly
identifies the direction, position, and extent of cloud shadows for
resolved cumulus and frontal stratus, with the documented failure modes
over open water, snow, and aerosol plumes.

We have refrained from claiming quantitative performance figures because
no independent ground truth has been used. The single most important
next step is GOES-East ABI validation — the same approach used by
Trees et al. (2022) against VIIRS — yielding precision, recall, and F1
on a representative sample of TEMPO scans. Beyond validation, in rough
order of expected scientific payoff:

1. **GOES-East ABI quantitative validation.** Co-locate TEMPO and GOES-East
   B2 (0.5 km) imagery for ten randomly chosen scans; compute F1 per
   cloud-type/surface stratum.
2. **Explicit quality masking.** SZA < 75°, snow_ice_fraction ≤ 0.5, and
   CLDO4 `processing_quality_flag` error bits, applied before the
   algorithm runs.
3. **Brightness gate for ACSF.** Require GLER466 > 0.05 (i.e. the surface
   should be bright enough that a shadow is meaningful) before firing
   ACSF. This is the cheapest defence against open-water false positives.
4. **Multi-wavelength surrogate.** Add an analogous SceneLER440 vs GLER440
   check, requiring the contrast to be present at both 440 and 466 nm.
   This would discriminate aerosol darkening (steeper spectral slope) from
   shadow darkening (flat spectral slope).
5. **Polygonal umbra projection.** Replace the Bresenham line with a true
   four-corner umbra polygon, with cluster-level union before rasterization
   so that adjacent cloud-source pixels combine into one continuous
   polygon.
6. **MERRA-2-based height.** Replace the constant scale height with a
   co-located MERRA-2 pressure-altitude profile for OCP-to-height
   conversion.
7. **GCP-based GeoTIFF georeferencing.** Use `latitude_bounds`/
   `longitude_bounds` corners directly through GDAL warp for pixel-perfect
   georeferencing.

In the longer term, the most rigorous path is to replace the
single-wavelength ECF surrogate with a full SCNLER computation from L1B
radiances and a Rayleigh-correction LUT, evaluated at all 13 DARCLOS
wavelengths. This requires a sustained operational dependency on the LUT
infrastructure, which is currently impractical for individual research
groups but feasible as part of an SDPC-internal pipeline.

---

## Code and data availability

The DARCLOS-TEMPO source code, configuration files, methodology technical
report, and example outputs are openly available at
[repository URL — TBD]. The pipeline depends on TEMPO V04 L1B and CLDO4
L2 V04 data, which are available through the NASA Atmospheric Science
Data Center (ASDC; <https://asdc.larc.nasa.gov>) and the TEMPO Science
Data Processing Center.

## Author contributions

[TBD]

## Competing interests

The authors declare no competing interests.

## Acknowledgements

We thank the TEMPO Science Team and the CLDO4 algorithm developers
(SAO/SDPC) for making the operational L1B and L2 products publicly
available and for valuable conversations on the OCP retrieval and the
SceneLER/GLER consistency check that motivates our ACSF surrogate.

## References

- Boersma, K. F., et al. (2018). Improving algorithms and uncertainty
  estimates for satellite NO₂ retrievals: results from the quality
  assurance for the essential climate variables (QA4ECV) project.
  *Atmospheric Measurement Techniques* 11, 6651–6678.
- González Abad, G., et al. (2015). Updated Smithsonian Astrophysical
  Observatory Ozone Monitoring Instrument (SAO OMI) formaldehyde
  retrieval. *Atmospheric Measurement Techniques* 8, 19–32.
- Joiner, J., Vasilkov, A. P., Bhartia, P. K., Wind, G., Platnick, S., &
  Menzel, W. P. (2012). Detection of multi-layer and vertically extended
  clouds using A-Train sensors. *Atmospheric Measurement Techniques* 5,
  351–369.
- Nowlan, C. R., et al. (2025). TEMPO NO₂ ATBD: Tropospheric NO₂ from
  DOAS. TEMPO Algorithm Theoretical Basis Document.
- Stammes, P., Sneep, M., De Haan, J. F., Veefkind, J. P., Wang, P., &
  Levelt, P. F. (2008). Effective cloud fractions from the Ozone
  Monitoring Instrument: theoretical framework and validation. *Journal
  of Geophysical Research* 113, D16S38.
- Tilstra, L. G., Tuinder, O. N. E., Wang, P., & Stammes, P. (2017).
  Surface reflectivity climatologies from UV to NIR determined from Earth
  observations by GOME-2 and SCIAMACHY. *Journal of Geophysical Research:
  Atmospheres* 122, 4084–4111.
- Trees, V. J. H., Wang, P., & Stammes, P. (2022). DARCLOS: a cloud
  shadow detection algorithm for TROPOMI. *Atmospheric Measurement
  Techniques* 15, 3121–3140. https://doi.org/10.5194/amt-15-3121-2022.
- Vasilkov, A., Joiner, J., Spurr, R., Bhartia, P. K., Levelt, P., &
  Stephens, G. (2008). Evaluation of the OMI cloud pressures derived
  from rotational Raman scattering by comparisons with other satellite
  data and radiative transfer simulations. *Journal of Geophysical
  Research* 113, D15S19.
- Vasilkov, A., Qin, W., Krotkov, N., Lamsal, L., Spurr, R., Haffner,
  D., Joiner, J., Yang, E.-S., & Marchenko, S. (2017).
  Geometry-dependent Lambertian-equivalent reflectivity for surface
  reflectance applied to BRDF surfaces. *Atmospheric Measurement
  Techniques* 10, 333–349.
- Vasilkov, A., et al. (2018). Cloud optical centroid pressure from
  the OMI 477 nm O₂-O₂ band: an updated algorithm. *Atmospheric
  Measurement Techniques* 11, 4093–4107.
- Wallace, J. M., & Hobbs, P. V. (2006). *Atmospheric Science: An
  Introductory Survey* (2nd ed.). Academic Press.
- Wang, H., Nowlan, C. R., González Abad, G., Chong, H., Hou, W., Houck,
  J. C., Liu, X., Chance, K., Yang, E.-S., Vasilkov, A., Joiner, J., Qin,
  W., Fasnacht, Z., Knowland, K. E., Chan Miller, C., Spurr, R. J. D.,
  Flittner, D. E., Carr, J. L., Suleiman, R. M., Davis, J. E., &
  Fitzmaurice, J. A. (2025). Algorithm Theoretical Basis for Version 3
  TEMPO O₂-O₂ Cloud Product. *Earth and Space Science* 12, e2024EA004165.
  https://doi.org/10.1029/2024EA004165.
- Zoogman, P., Liu, X., Suleiman, R., et al. (2017). Tropospheric
  Emissions: Monitoring of Pollution (TEMPO). *Journal of Quantitative
  Spectroscopy and Radiative Transfer* 186, 17–39.

---

## Appendix A — Algorithm parameters

| Parameter | Symbol | Value | Source |
|---|---|---|---|
| Cloud-source ECF threshold | $\tau_{\rm cloud}$ | 0.30 | TEMPO cloud team recommendation |
| Shadow ECF threshold (ACSF surrogate) | $\tau_{\rm shadow}$ | 0.05 | DARCLOS-TEMPO; tuned for V04 |
| Safety factor | $C$ | 0.5 | Trees et al. (2022) Eq. 1 |
| Hypsometric scale height | $H_{\rm scale}$ | 8500 m | Standard troposphere |
| Cloud altitude cap | $h_{\rm cap}$ | 16 000 m | Tropopause guard |
| Max drop fraction (per granule or scan) | $f_{\rm drop\,max}$ | 0.10–0.30 | Empirically tuned per V0x |
| Cloud Lambertian albedo (in CLDO4) | $R_c$ | 0.8 | CLDO4 ATBD |
| Earth radius (M, N) | — | 6 378 137 m | WGS-84 equatorial |

## Appendix B — Output file conventions

Per granule (`run_day.py`):

```
{output_root}/{YYYY}/{MM}/{DD}/
├── rgb_<L1_basename>.tif
├── <L1_basename>_clouds.shp                 (+ .dbf, .shx, .prj, .cpg)
├── <L1_basename>_potential_shadows.shp
└── <L1_basename>_actual_shadows.shp
```

Per scan (`run_scan.py`):

```
{output_root}_scan/{YYYY}/{MM}/{DD}/
├── rgb_S<scan>.tif
├── S<scan>_clouds.shp
├── S<scan>_potential_shadows.shp
└── S<scan>_actual_shadows.shp
```

All shapefiles are EPSG:4326. The GeoTIFF affine transform is derived
from the bounding box of the granule (or scan) lat/lon corners using
`rasterio.transform.from_bounds`. Per-feature attributes include
`type`, `name`, `value`, `source` (granule or scan identifier), and
`area_deg2`.

