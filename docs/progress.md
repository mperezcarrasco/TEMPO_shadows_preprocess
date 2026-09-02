# Progress log

Maintained by Claude. Read this at the start of every session before doing
anything else. Newest entries first.

## 2026-09-01 — Methodology redesign decided; migration to the VM

User judged §3 ad-hoc (unjustified parameters, visual-only validation, few
local scenes, no V03/V04 evidence). Brainstormed and approved a two-tier
GOES-ABI validation design (docs/specs/2026-09-01-validation-methodology-
design.md): 6-8 hand-labeled ABI scenes scored DARCLOS-style (O, C, F1),
leave-one-scene-out CV for tau_cloud/tau_shadow/C, automatic corpus-wide
ABI darkening check, V04 re-run on a ~20-day subset of V03 days for the
version question, ABI-based checks for H_scale/h_cap. Pairing via the
TEMPO-ABI Synergy tool (L1B RAD input only — the tool sets h=0 for L2
inputs; per-mirror-step scene choice; clear-in-both-views scoring rule;
pairing QA gate). Corpus (processing_status.csv): 105 days / 1,448 scans,
92 V03 days (Aug 2023-Mar 2025) + 13 V04 days (Sep 2025), no overlap.
Wrote docs/handoff_vm.md; CLAUDE.md §0 updated and the "angles from L1B"
item flagged as contradicted. Committed docs/, notebooks/paper_figures.ipynb
and fig_pipeline.drawio (force-added; .gitignore ignores docs/ and
notebooks/). Work continues on the VM.

## 2026-09-01 — Methodology (§3) audit

User applied all three Background follow-ups (OCP cap wording,
tilstra2022dlerreport, "is adapted from") — §1 and §2 are closed.
§3 audited against the code (scripts/ + configs/), DARCLOS, the CLDO4
ATBD, and the local granule files. Code-facing claims all verified
(heights, thresholds, projection, k-d tree, Bresenham, ACSF AND,
drop-frac guard, per-scan concat, h5py/fiona rationale).

**Major contradiction (needs server check):** §3.4 + Overview item 3
claim L2 `viewing_azimuth_angle` is entirely fill-valued and
`solar_azimuth_angle` ~94% fill-valued in V03 and V04. On ALL 8 local
ASDC granules (4 × V03, 4 × V04) every L2 geolocation angle is 0%
fill and BIT-IDENTICAL to the L1B band-group angles. Claim likely came
from the server archive copies (subsetted?) — must be re-verified on
`/store/sao_atmos/TEMPO` before submission. Same claim also lives in
project CLAUDE.md §"Angles from L1B" (now suspect).

Other findings (§3): "~0.05–0.10 documented ECF bias" — ATBD actually
says clear-sky pixels *peak near ECF = 0.05*; "V04 reduces bias" is
OUR file-level finding (clear-median ECF 0.098–0.119 V03 →
0.039–0.068 V04 on the 4 granule pairs), not documented; τ_cloud=0.30
"recommended by TEMPO cloud team" unsourced (DARCLOS itself used
ECF > 0.05 for cloud pixels — departure never acknowledged);
"DARCLOS reference implementation iterates per pixel" unsupported (no
public DARCLOS code; paper doesn't describe one); scan-scale
M ≈ 3×10⁶ overstated (nominal scan = 1181 mirror positions × 2048 =
2.42×10⁶; S004 tif confirms 1181); "common for marine stratus"
overstated (p_cld ≥ p_sfc on only 0–5.3% of cloudy pixels locally);
"(pre-clipping in V03)" — V04 also clips (nonclipped_cloud_fraction
min −0.17…−0.27 in BOTH versions); A_scene ≈ A_GLER over-attributed
to ATBD (ATBD check is P_scene = P_sfc); appendix f_drop_max
"0.10–0.30" vs released config 0.10. Verified OK: bit 13 meaning,
granule duration 6 m 40 s, granule grid 131–132 × 2048 ≈ 2.7×10⁵,
N_source 7.7×10⁴–1.2×10⁵, hypsometric ~10% accuracy (standard-
atmosphere check: +7% at 500 hPa, +12% at 300 hPa with H = 8.5 km).
Suggestions delivered in chat; user edits Overleaf by hand.

## 2026-09-01 — Background third-pass audit: CLEAN

All fixes verified applied (h_c vs ellipsoid, convention sentence,
parallax direction, A_DLER + tilstra2021dler, \mathbf{y}_k typo,
appendix M/N row). Every §2 equation now matches its source exactly;
compile clean (0 errors, 0 undefined refs, 15 pages). New empirical
finding (S003G05, V03+V04): for ECF < 0.05, bit 02 set on 100% of
pixels and released cloud_pressure == min(ScenePressure,
surface_pressure) on 100%/99.7% of pixels — the OCP replacement holds
in BOTH versions but is CAPPED AT SURFACE PRESSURE (cap not in ATBD
text; file-verified). Suggested one-word-level refinement of the §2.3
sentence, plus two standing optional items (add tilstra2022dlerreport
for the TROPOMI DLER data; "inherits" vs "is adapted from").

## 2026-09-01 — Background second-pass audit

User applied the Background fixes (incl. δ/ϑ geodetic rewrite and
sec:projection renames). Second pass verified §2 against sources:
equations now all correct (eq:scnler = DARCLOS Eq. 10 exactly;
geodetic block = Eqs. 6–7 with closure/radians/definitions; §2.3
fully fixed). Remaining, reported in chat: (1) A_DLER undefined —
the DLER-comparison sentence was lost between eq:scnler and eq:gamma,
tilstra2021dler no longer cited in §2.2; (2) h_c misdefined "above
the surface" (must be w.r.t. WGS-84 ellipsoid, else h=(1+C)(h_c−h_sfc)
double-subtracts); (3) azimuth/axis convention sentence still missing;
(4) parallax sentence direction inverted (nadir projection displaced
from pixel centre, not cloud from nadir projection); (5) typo
\mathbf{y}k (missing _) in sec:projection; (6) appendix table row
still "Earth radius (M,N) WGS-84 equatorial".

## 2026-08-31 (late night) — Background section audit

Audited §2 (Background) claim-by-claim and formula-by-formula against
Trees et al. 2022 and Wang et al. 2025 (two parallel readers with
verbatim page/equation quotes), plus product-file checks. Confirmed
errors reported in chat for the user to fix by hand on Overleaf:
(1) SCNLER equation (eq:scnler) wrong — denominator must be
T + s*(R_meas − R0); manuscript has undefined "T_meas" and drops s*
from R0; acronym expansion is "Lambertian-equivalent reflectivity of
the scene", not "Scene Normalised..."; DAK RT code, not "lookup table".
(2) Triangle OPQ misidentified — O = cloud-pixel centre (apparent
cloud), P = nadir projection of cloud centroid (both surface points),
not "observer" and "cloud-top point"; flag within OR INTERSECTED BY,
repeated 4x at pixel corners. (3) DLER citation wrong — tilstra2017dler
is the GOME-2/SCIAMACHY LER climatology (in DARCLOS only cited for the
A_scene formalism); the DLER used is TROPOMI DLER v0.6 = Tilstra 2022
KNMI report S5P-KNMI-L3-0301-RP, theory Tilstra et al. 2021 (already in
bib as tilstra2021dler). (4) "Lambertian cloud at scene pressure" wrong
— I_c uses cloud at OCP (init 700 hPa, ECF-OCP iterated as coupled
pair, ≤5 passes); scene pressure is a different ATBD quantity.
(5) SceneLER paragraph — names not in ATBD (are in product files:
support_data/SceneLER440/466, long_name "reflectance calculated at
ScenePressure"; ScenePressure field exists); ATBD clear-sky check is
P_scene = P_s (pressure), not LER = GLER; scene pressure REPLACES OCP
in the released product when ECF < 0.05 (bit 02). (6) Safety-factor
rationale — C=0.5 empirically tuned to minimise PCSF omission error;
sub-pixel structure handled by corner repetition, not by C.
(7) "M ≈ N ≈ 6378137 m" is the WGS-84 semi-major axis, not a radius of
curvature, and is our simplification (max 0.7% off), not DARCLOS's.
(8) SCSF: per-wavelength flags (AAI 340/380, NO2 440 named), not
"per-window ... NO2, HCHO, SO2, O3"; unvalidated auxiliary product.
(9) OCP "near 477 nm", fit window 439–488 nm; ECF/OCP not "separate".
Correct as written: parallax/displacement/geodetic equations (DARCLOS
Eqs. 2–7 incl. h_sfc terms), safety-factor Eq. 1, Γ/λmax/−15% (Eqs.
11–13), MLER Eq. 1, R_c = 0.8, ECF at 466 nm, negative-ECF clipping.
Empirical (S003G05 V04): median SceneLER466−GLER466 = −0.012 on clear
non-PCSF pixels (87% negative; median clear GLER 0.049) vs −0.018 on
ACSF pixels — "equals GLER when clear" is idealized; separation weak.

## 2026-08-31 (night) — Introduction re-audit after user edits

User applied the audit corrections by hand on Overleaf (synced to git,
commit "Apply introduction audit corrections"). Re-audit: 17/18 items
now correct; compile clean (0 errors, 0 undefined citations, 0 bibtex
warnings, 15 pages); all 5 new bib entries match Crossref. Two residual
items reported in chat: (1) P1 "The full field of regard is scanned
once per hour" dropped the "during the middle of the day" qualifier —
per Chong 2026, morning/afternoon optimized scans are ~40 min over
about two-thirds of the FOR; (2) the new bib entries (Copernicus/AGU
exports) lack brace protection, so abbrvnat lowercases acronyms in the
reference list ("dler", "gome-2", "tropomi", "tempo level 0-1") —
verified in output.bbl; chong entry also has doi-as-URL + abstract
clutter.

## 2026-08-31 (evening) — Introduction claim audit

Audited every claim in the Introduction against sources (5 parallel
readers over: Trees et al. 2022 DARCLOS PDF; Zoogman et al. 2017;
Wang et al. 2025 CLDO4 ATBD; Nowlan et al. 2025 NO2 ATBD; Chong et al.
2026 L0-1 ATBD) plus local-file checks. NEW WORKFLOW: the user now makes
all manuscript edits by hand on Overleaf; Claude proposes text in chat
only (recorded in CLAUDE.md §0). Corrections proposed in chat, main
confirmed errors: TROPOMI pixel size (7.2x3.6 / 5.6x3.6, not 7x3.5);
DARCLOS "quote" not verbatim; FRESCO-S wrong (FRESCO centroid height,
safety-inflated); SCSF is 13 fixed wavelengths 328-494 nm, not per-DOAS
flags; F1 0.84-0.95 is ACSF-only vs manual VIIRS inspection, low scores
from thin/small clouds; "operational since Aug 2023" wrong (first light
1-2 Aug 2023, nominal ops 19 Oct 2023); "Greater Antilles" overstates
Zoogman's "Cuba and the Bahamas"; resolution 2.0x4.75 km must cite
Chong 2026 (Zoogman has design values 2.1x4.4 at 100W). Empirical:
L1B cloud_top_height 100% fill on all 4 local V04 granules; GLER/
SceneLER/SurfaceLER exist at exactly 440+466 nm in V03 and V04 L2.
New refs verified via Crossref: Chong 2026 (10.1029/2025EA004516),
Qin 2019, Fasnacht 2019, Tilstra 2021, Ludewig 2020. Also flagged for
other sections: sec:acsf bias "0.05-0.10" should be "peak near 0.05"
(V04-improvement claim unsourced); limitations "smoke and dust" -> ATBD
says smoke only, and cite Sect. 3.2.1 not 3.1; OCP "near 477 nm";
Background DLER citation should be Tilstra 2021/2022, check
tilstra2017dler; NO2 ATBD never mentions shadows (good motivation).

## 2026-08-31 (later still) — Overleaf linked to GitHub

Linked the Overleaf project to a new **private** GitHub repository
`mperezcarrasco/TEMPO_shadows` via Overleaf's GitHub integration (the
user's Overleaf account was already connected to GitHub, so no OAuth was
needed). Pushed the current project state (commit "Add figures and
captions; fix float placement (ht!)") and cloned it to
`/Users/maperezc/Downloads/TEMPO/TEMPO_shadows/` over HTTPS (stored
keychain credentials; the SSH key on this Mac is not authorized for this
repo). Verified the clone: all 4 figure PDFs byte-identical to the local
originals, tex has the `ht!` and `0.6\linewidth` fixes. CLAUDE.md §0
standing instruction rewritten around the git workflow. Caveat recorded
there: **Overleaf↔GitHub sync is manual in both directions** via the
project's GitHub dialog.

## 2026-08-31 (later) — Figure PDFs uploaded; float placement fixed

User uploaded the 4 figure PDFs to the Overleaf `figures/` folder. First
compile put all figures at the document end: `fig_pipeline` at
`width=0.8\linewidth` was ~8.4 in tall, exceeding the `[tb]` top-float
limit (~6.8 in), so it could never be placed and blocked the ordered
float queue behind it. Fix (applied on Overleaf, user-chosen spec): all
four `\begin{figure}[tb]` → `[ht!]`, and the pipeline schematic reduced
to `width=0.6\linewidth`. Verified from the compile log: 0 errors,
14 pages, `fig_pipeline` ships around p. 4 and the three data figures
around p. 8 — near their references, no longer at the end. 4 overfull
hbox warnings remain (minor, not from the figures).

## 2026-08-31 — Manuscript figures generated; Overleaf updated

**Goal:** generate the four manuscript figures (all were `\placeholderfig`
placeholders) without modifying the codebase.

**Done:**

- New notebook `notebooks/paper_figures.ipynb` (runs top-to-bottom in
  `/Users/maperezc/Downloads/env`; imports `scripts/shadows.py` and
  `scripts/io_utils.py` unmodified; git hash at run time: `6cd3a78`).
  Produces, in `docs/paper/figures/`:
  - `fig_granule_morning.pdf` — S003G05, 2025-09-09 12:52 UTC. Cloud
    89,437 px (33.3 %), PCSF 32,032 (11.9 %), ACSF 12,671 (4.7 %).
  - `fig_granule_afternoon.pdf` — S014G02, 2025-09-09 23:12 UTC, run with
    `max_drop_frac = 0.15` (10.4 % invalid heights; guard only). Cloud
    77,715 (28.7 %), PCSF 37,640 (13.9 %), ACSF 13,229 (4.9 %).
  - `fig_scan_S004.pdf` — scan S004 of 2025-09-17 from
    `results_scan_scan/2025/09/17/` (user-confirmed produced with the
    ECEF k-d-tree code). 9 granules (from 1,181 merged rows); 8,305
    cloud / 17,198 PCSF / 5,970 ACSF polygons. Display cropped to
    135–55° W, 17–62° N.
  - Both granule figures display-cropped to ≥ 30° N (no-data wedge below;
    user-requested).
- Oracles run and passed: ACSF ⊆ PCSF on both granules; shadow-direction
  check (morning SAA +92.2° → mean shadow dlon −0.406° westward;
  afternoon SAA −92.9° → +0.492° eastward).
- Pipeline schematic `fig_pipeline.drawio` + `fig_pipeline.pdf` (draw.io
  desktop CLI export) in `docs/paper/figures/`.
- **Overleaf paper.tex edited in place** (project 6a20d7d9684177f5ea1c4c35,
  history v13→v14): the four `\placeholderfig` blocks replaced with
  `\includegraphics{figures/…}` + full captions; one sentence appended to
  §4.1 (Data) stating the per-granule examples come from 9 Sep 2025
  development granules. A `figures/` folder was created in the project.
  Cross-granule-boundary highlight was DROPPED from the fig:scan-mosaic
  caption (boundary rows untraceable: no run log for the 2025-09-17 run).

**Failed / blocked:**

- Could not upload the figure PDFs to Overleaf programmatically: the
  in-app browser blocks localhost fetches, Overleaf session cookies are
  HttpOnly, and base64-relaying MB-scale binaries through the JS console
  is corruption-prone. **USER ACTION REQUIRED: drag the 4 PDFs from
  `docs/paper/figures/` into the `figures` folder on Overleaf, then
  recompile.** Until then the Overleaf compile shows missing-file errors.
- S014G02 fails the default `max_drop_frac = 0.10` (10.4 % invalid
  heights) — documented in the fig. 3 caption and the notebook header.

**Flagged (evidence contradicting the manuscript, NOT yet fixed):**

- §4.2 claims ACSF = 4–10 % of cloud-source pixels and 0.5–2 % of all
  pixels. The two 2025-09-09 granules give 14.2 % / 17.0 % of
  cloud-source and 4.7 % / 4.9 % of all pixels — outside both ranges.
  The corpus-wide numbers must be recomputed from the actual
  17–18 Sep 2025 run (data on `/store/sao_atmos/TEMPO`) before
  submission. Left untouched in the manuscript.

**Next:**

1. User uploads the 4 PDFs to Overleaf `figures/` and recompiles.
2. Recompute §4.2 corpus statistics on the server; fix the text.
3. Remaining pre-submission items from CLAUDE.md §0: affiliations,
   CRediT contributions, repository URL, Copernicus class if AMT.

**Stale after this session:** `docs/paper/paper.tex` and
`docs/paper_draft.md` local snapshots (predate today's Overleaf edits).
