# Handoff to the VM session — read first

Written 2026-09-01 on the laptop. The VM holds the full corpus, all V03/V04
runs, and the synergy tool; the laptop session ends here.

## Standing rules (from the user)
- The user makes ALL manuscript edits by hand on Overleaf. Claude proposes
  text in chat with exact location + current line + replacement. Read the
  manuscript via GitHub: Overleaf -> Menu -> GitHub -> "Push Overleaf changes
  to GitHub", then `git pull` in the `TEMPO_shadows` clone.
- Show the full draft of any document/config in chat before writing it.
- Research-integrity rules of ~/.claude/CLAUDE.md apply (fail loudly, no
  silent defaults, every number traceable to a command).

## Where things are
- Code: this repo (`TEMPO_shadows_preprocess`). `scripts/` unchanged since
  commit 6cd3a78; `notebooks/paper_figures.ipynb` makes the manuscript figures.
- Manuscript: github.com/mperezcarrasco/TEMPO_shadows (Overleaf-linked).
- Design: `docs/specs/2026-09-01-validation-methodology-design.md`.
- Log: `docs/progress.md` (newest first). Update before ending a session.
- Synergy tool: cloned on the VM; the laptop's patched wrapper and notes are
  in `abi_tempo/` (CLAUDE.md there lists known tool bugs: L2 input -> h=0,
  granule-edge NaN columns, filename quirks, tmp folder collisions).
- References to fetch on the VM (open access): DARCLOS
  doi:10.5194/amt-15-3121-2022; CLDO4 ATBD doi:10.1029/2024EA004165; L0-1
  ATBD doi:10.1029/2025EA004516. Put PDFs in `docs/`, not in git.

## State of the manuscript (as of 2026-09-01)
- §1 Introduction and §2 Background: audited claim-by-claim, all fixes applied.
- §3 Methodology: audited; findings delivered but NOT applied because §3 is
  being redesigned (see design doc). Findings still valid for the rewrite:
  L2-azimuth fill claim contradicted by ASDC files (see first task); ECF
  bias misquote (ATBD: clear pixels peak near ECF = 0.05); tau_cloud = 0.30
  unsourced and DARCLOS used 0.05; "DARCLOS reference implementation"
  unsupported; scan M = 2.4e6 not 3e6; "common for marine stratus"
  unsupported (0-5 %); V04 also clips ECF; A_scene ~ A_GLER over-attributed.
- §4 Results: corpus statistics (4-10 % / 0.5-2 %) untraceable; will be
  replaced by the new validation results.
- Pre-submission: affiliations, CRediT, repository URL, Copernicus class.

## First tasks
1. Run on one V03 and one V04 CLDO4 file from the server archive:
   fill fraction of geolocation/solar_azimuth_angle and viewing_azimuth_angle.
   Laptop ASDC files: 0 % fill, bit-identical to L1B. Outcome decides the
   §3.4 rewrite and a CLAUDE.md correction (item "Angles from L1B").
2. Corpus inventory from processing_status.csv + results dirs; confirm
   partial days; list Jan-Feb days with snow candidates.
3. Design doc section 12 in order.

## Laptop facts worth keeping
- Per-granule N_source 0.8-1.2e5; grid 131-132 x 2048; scan 1,181 x 2048.
- Clear-pixel median ECF: V03 0.10-0.12, V04 0.04-0.07 (4 granule pairs).
- Released cloud_pressure == min(ScenePressure, surface_pressure) when
  ECF < 0.05 (bit 02), both versions.
- Figures: S003G05 and S014G02 of 2025-09-09 (max_drop_frac 0.15 for the
  latter), scan S004 of 2025-09-17.
