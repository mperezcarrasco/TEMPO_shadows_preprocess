# DARCLOS-TEMPO validation and parameter-selection protocol — design

Date: 2026-09-01
Status: approved in conversation (brainstorm 2026-09-01); text approved 2026-09-01
Project: `TEMPO_shadows_preprocess` (code), `TEMPO_shadows` (manuscript, Overleaf)
Execution: on the VM, where the full corpus and the synergy tool live

## 1. Why

The manuscript's Methodology (§3) fixes every algorithm parameter without a
selection criterion and validates by visual inspection of a few local scenes.
This design replaces that with the validation logic of the parent paper (Trees
et al. 2022 validated PCSF/ACSF against manually identified shadows in VIIRS
true-colour imagery, reporting omission O, commission C and F1, and chose q =
-15 % as the value maximizing the detection score) using GOES-R ABI as the
reference instrument, which views the same domain continuously at 0.5 km.

## 2. Decisions taken

- Strategy A: two-tier ABI validation (labeled scenes + automatic corpus check).
- 6-8 hand-labeled scenes; hyperparameters by leave-one-scene-out cross-validation.
- Pairing through the TEMPO-ABI Synergy tool v1.4.1 (patched fork in
  `abi_tempo/`), ABI from public AWS buckets.
- V03-vs-V04 answered by re-running V04 CLDO4 on a stratified ~20-day subset of
  the V03 days (no date is processed in both versions today).
- H_scale and h_cap remain physical constants, each with a direct ABI-based
  check; C is the only height parameter in the tuning grid.
- User edits the manuscript by hand on Overleaf; Claude proposes text in chat.

## 3. Corpus facts the design rests on (processing_status.csv, 2026-08-31)

| fact | value |
|---|---|
| days / scans / granules processed | 105 / 1,448 / 10,960 |
| V03 days | 92: Aug-Sep 2023 (26), Jan-Feb 2024 (24), May-Sep 2024 (38), Jan+Mar 2025 (4) |
| V04 days | 13: 17-30 Sep 2025 |
| days in both versions | 0 |
| partial days | 2023-08-17 (2/7 scans failed), 2025-09-25 (8 scans), 2025-09-27 (3 scans) |
| winter days (Jan-Feb) | 25 -> snow scenes expected |
| granule | 131-132 mirror steps x 2048; nominal scan 1,181 steps (Chong et al. 2026) |
| TEMPO INR requirement | 82 urad (0.6 px EW, 2 px NS); performance sub-pixel |

## 4. Pairing rules (Tier 0)

Synergy tool invocation, per scene: input = TEMPO **L1B RAD** granules (never
CLDO4 L2: the tool sets terrain height h = 0 for L2 inputs, `ABI_TEMPO_synergy_func1.py:68`,
which displaces ABI by h_terrain*tan(VZA) over mountains); `--vza_vaa 1`;
`--imgNeighbor_options "-1" 0 1`; GOES-East (G16 before Apr 2025, G19 after)
east of ~110 W, GOES-West (G18) where GOES-East VZA > 65 deg. Products: CMIP
C01/C02/C03, ACMF, ACHA2KMF, ACHP2KMF, COD2KMF, ACTPF, CCLF, FSCF, ADPF.

Time matching: the tool picks the full-disk scene nearest the granule midpoint
(10-min cadence). We refine to per-mirror-step by choosing, for each mirror
step, the predecessor/concurrent/successor scene nearest its own timestamp.
Residual offset (scene skew + step spread): 3-8 min, i.e. 2-5 km of cloud
drift at 10 m/s = 0.5-1 EW pixel, 1-2.5 NS pixels. Handled by (a) the
per-step choice, (b) reporting F1 with and without a 1-pixel tolerance, (c)
optional motion shift from the predecessor-successor pair when scene motion
exceeds 1 pixel.

Scoring domain: a TEMPO pixel is scored only if it is (i) not a cloud pixel
in TEMPO (ECF < tau_cloud), (ii) clear in the ABI cloud mask, (iii) covered by
valid ABI data (`abi_valid`; the tool leaves the first/last mirror step of
each granule NaN), (iv) not in the glint mask (ABI VZA/VAA + solar angles),
(v) not in a terrain-shadow mask when SZA > 65 deg, (vi) not snow/ice (FSC,
ADP SnowIce) unless the scene is the snow stratum, (vii) not smoke/dust (ADP).
Rule (i)+(ii) is the "clear in both views" condition: shadows have no
parallax but the occluding cloud does.

## 5. Pairing QA gate (before any scoring)

Per scene, automatic: (1) TEMPO red vs ABI C02 (binned) cross-correlation
offset over clear land < 0.5 px both axes; (2) same test over terrain
> 1,500 m, no offset scaling with terrain*tan(VZA); (3) per-step ABI-TEMPO
offset logged, scene motion estimated from predecessor->successor, flag if
|v|*dt > 1 px; (4) TEMPO ECF vs ABI cloud probability monotonic. Visual: one
PNG per scene (TEMPO RGB | ABI true colour | PCSF/ACSF on ABI | difference)
and `review.csv` (registration_ok, shadows_visible, glint, terrain_shadow,
snow, notes). A scene enters Tier 1 only if 1-4 pass and the review is done.

## 6. Tier 1 - labeled truth and metrics

Scene selection: seeded stratified draw over the corpus, strata = time of day
(high-SZA morning / midday / late afternoon) x surface (land / ocean /
coastal) + one Jan-Feb snow scene; 6-8 scenes total, at least one per
stratum, across >= 3 months. Labeling: shadow polygons drawn on the 0.5-km
ABI true-colour image (QGIS: ABI GeoTIFF + TEMPO pixel-polygon shapefile). A
TEMPO pixel is "shadow" if >= 50 % of its footprint is covered, "partly" for
10-50 %, "clear" below 10 %. Following DARCLOS: missing a shadow pixel is an
omission, flagging a clear pixel a commission, partly-shadowed pixels count
in neither. One scene is relabeled blind after a week to report
labeler self-agreement. Metrics per scene and pooled: O, C, F1 for PCSF and
ACSF, strict and 1-px tolerant.

## 7. Parameter selection

Grid: tau_cloud in {0.05, 0.10, 0.20, 0.30, 0.40} (includes DARCLOS's 0.05),
tau_shadow in {0.02, 0.05, 0.08, 0.12}, C in {0, 0.25, 0.5, 0.75, 1.0}.
Leave-one-scene-out: tune on n-1 scenes (max pooled ACSF F1), evaluate on the
held-out scene; report CV-mean F1 and spread; freeze the parameters chosen on
all scenes; report 1-D sensitivity curves. H_scale, h_cap, max_drop_frac are
not tuned. Any change to the released defaults is a result, recorded in the
appendix table with its criterion.

## 8. Tier 2 - automatic corpus-wide check

For every ACSF pixel in the full runs: ABI C02 reflectance (cos-SZA
normalized) minus the same ABI pixel at the nearest time within +-2 h when
neither cloud nor PCSF is flagged (temporal clear reference). Control: clear
non-PCSF pixels per scene with matched SZA. "Confirmed darkening" = drop below
the control's 5th percentile (threshold derived from the control, not set by
hand). Report confirmed-darkening rate for ACSF vs control false rate, per
scan hour, per month, per version. Masks of section 4 apply. Pixels without a
reference are counted and excluded, not filled.

## 9. V03 vs V04

Re-run the pipeline with V04 CLDO4 on a stratified ~20-day subset of the V03
days (same L1B; subset includes every Tier-1 scene). Identical frozen
parameters. Compare: Tier-1 O/C/F1 per version on the labeled scenes; Tier-2
rates per version over the subset; clear-pixel ECF distributions. One table
answers the version question.

## 10. Height checks

- H_scale: apply the hypsometric formula to ABI cloud-top pressure (ACHP2KMF)
  and compare with ABI cloud-top height (ACHA2KMF) for the same pixels over
  the corpus; report residual by season. No reanalysis needed.
- h_cap: corpus percentile of hypsometric heights above 16 km; literature on
  OCP sitting below the physical top (Joiner et al. 2012; Vasilkov et al. 2008).
- C: distribution of (ABI ACHA height - our OCP-derived height) over the
  labeled scenes = the error budget (1+C) must cover; cross-check against the
  CV-chosen C.

## 11. Deliverables for the manuscript

Tables: labeled-scene inventory with strata and QA results; O/C/F1 per scene
(PCSF, ACSF, strict/tolerant), CV summary; parameter table with criterion;
V03-vs-V04. Figures: sensitivity curves; Tier-2 darkening distributions ACSF
vs control; height residuals; one labeled-scene example with ABI truth.
Every number traceable to a script and a logged run (docs/progress.md).

## 12. Work order on the VM

1. Inventory + the §3.4 L2-azimuth fill check on the server files.
2. Synergy pairing on one scene end-to-end (L1B input); QA gate on it.
3. Tier 2 on the existing full runs.
4. Scene selection -> pairing + QA for 6-8 scenes -> labeling -> Tier 1 + CV.
5. V04 subset rerun -> version comparison. Height checks.
6. Manuscript §3/§4 rewrite proposals (chat); user edits Overleaf.

## 13. Out of scope

Polygon umbra, cast/classify threshold decoupling, MERRA-2 heights, SCSF,
cloud-motion correction beyond section 4(c). Unchanged from the current
Limitations section.

## 14. Open items

- Exact ABI scan-time model per pixel (full-disk timeline) for the per-step
  matching; fallback is file midpoint.
- DEM source for the terrain-shadow mask (TEMPO L2 terrain_height is coarse).
- Whether the ABI cloud mask misfires inside shadows (check on scene 1).
