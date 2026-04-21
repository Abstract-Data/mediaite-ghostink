# Changelog

## [0.3.0] - 2026-04-20
### Added
- Expanded from 7 to 10 notebooks with three new forensic notebooks:
  - `00_power_analysis.ipynb` — pre-registration (hypotheses, thresholds, power analysis documented before analysis runs)
  - `02_corpus_audit.ipynb` — chain of custody (corpus hashing, Wayback spot-checks, duplicate analysis, archive integrity)
  - `08_control_comparison.ipynb` — confound elimination (control author comparison, topic drift covariate, outlet-wide vs. author-specific signals)
- Mandatory forensic header cell pattern for all notebooks (forensic question, input/output artifacts, run metadata with config hash and corpus hash)
- Cell ordering pattern: hypothesis → code → interpretation → summary finding
- `src/forensics/utils/provenance.py` module (`compute_config_hash`, `compute_corpus_hash`, `get_run_metadata`)
- Quarto `type: book` format with four parts (Data Collection & Audit, Exploration & Features, Analysis, Evidence & Conclusions)
- `index.qmd` landing page spec
- New tests: provenance hash determinism, index.qmd existence, 10-notebook count verification

### Changed
- Renumbered notebooks: old 02→03, 03→04, 04→05, 05→06, 06→07, 07→09
- Quarto config switched from `type: website` to `type: book` with `output-dir: data/reports`
- Simplified `quarto-build` Makefile target

## [0.2.0] - 2026-04-20
### Added
- feat: add expert-witness-grade methodology appendix, FindingStrength confidence taxonomy for non-technical readers, pre-registration document template

## [0.1.0] - 2026-04-20
### Added
- Initial spec: 7 Jupyter notebooks, Plotly chart theme, Quarto config, Makefile, Git LFS, Cloudflare Pages deployment.
