# DARCLOS-TEMPO paper — LaTeX sources

This directory holds the LaTeX sources for the DARCLOS-TEMPO methods
paper, derived from `docs/paper_draft.md`.

```
paper.tex          Main document
references.bib     Bibliography (BibTeX)
figures/           Drop final figure files here
Makefile           Build helpers
README.md          This file
```

## Compiling

The document builds with any standard TeXLive distribution; no
Copernicus-specific packages are required. From this directory:

```bash
make           # produces paper.pdf
make watch     # rebuilds on every save (requires latexmk)
make clean     # removes intermediate files
make distclean # also removes paper.pdf
```

Or, without `make`:

```bash
pdflatex paper
bibtex   paper
pdflatex paper
pdflatex paper
```

## Placeholder figures

Every figure in the manuscript is currently a grey dashed-border
placeholder produced by the `\placeholderfig` macro defined in
`paper.tex`. The caption inside the placeholder describes what the
figure should show. To insert a real figure later, replace the
`\placeholderfig[<height>]{<description>}` line inside the relevant
`figure` environment with

```latex
\includegraphics[width=\linewidth]{figures/<filename>}
```

keeping the surrounding `\caption{...}` and `\label{fig:...}` unchanged.

## Targeting a specific journal

The document uses the standard `article` class so it compiles
everywhere out of the box. For AMT submission, swap the preamble's
`\documentclass{article}` line for the Copernicus class

```latex
\documentclass[amt,manuscript]{copernicus}
```

(which requires the `copernicus` package and changes `\bibliographystyle`
to `copernicus`).

For ESS, JGR, or other AGU journals, swap to the AGU template instead.
The body of the manuscript (sections, equations, references, figure
captions) does not depend on the class choice.

## Citations

References are managed in `references.bib`. The four key citations are

- `trees2022darclos` — the original DARCLOS paper
- `wang2025cldo4` — the CLDO4 V3 ATBD
- `vasilkov2018cldo` — the OMI O₂-O₂ algorithm that CLDO4 inherits from
- `zoogman2017tempo` — the TEMPO mission paper

All other entries (`vasilkov2017gler`, `tilstra2017dler`,
`stammes2008omi`, `joiner2012a-train`, `boersma2018qa4ecv`,
`gonzalezabad2015hcho`, `wallace2006atmospheric`,
`nowlan2025no2atbd`) appear in the body and are listed in the
bibliography.

## Word count target

The current draft is ~5500 words (excluding references and
appendices), which fits within AMT's typical length expectations.
The Limitations section is intentionally substantial; if reviewers
push for shorter, the natural cut is to compress \S 5.1 and \S 5.2
into a single paragraph each and move the detail into a supplement.
