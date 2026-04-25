# Changelog — Report Visual Polish

## [0.1.0] — 2026-04-24

**Model:** claude-opus-4-7
**Status:** active
**Bump reason:** initial release.

### Added

- Initial prompt covering the Quarto PDF production pass for the bound
  forensics report. Scope: typography, table rendering, chart consistency,
  cover page, page layout, and front-matter only — no analysis-code edits.
- Seven required fixes in execution order: PDF engine + font swap
  (xelatex, Pagella/Inter/JetBrains Mono, scrartcl class with running
  headers/footers and continuous page numbering); cover page via
  `before-body.tex` with metadata table and CONFIDENTIAL banner; replace
  every Polars `print()` table with `Markdown(df.to_markdown())` or
  `great_tables`; unify chart rendering on matplotlib via a shared
  `notebooks/_styles.py` (Plotly removed from PDF path entirely);
  per-chart fixes for the heatmap (p6), line chart (p11), histogram
  (p12), and bar chart (p17); figure/table numbering with `@fig-` cross
  references; `seqsplit`-based path-break handling and tinted inline-code
  background; `scrartcl` swap to eliminate forced chapter page breaks.
- Acceptance criteria (10 items) and verification commands (xelatex
  build, schema-row leak check, Plotly-residue check, page-count diff).
- Out-of-scope list explicitly preserves stage boundaries, the data
  model, the prose narrative, and the HTML render path.
