# Changelog — Phase 12: Survey Mode, Interactive TUI, Runtime Hardening & Calibration

## [0.1.0] — 2026-04-21

**Model:** claude-opus-4-6
**Status:** pending

### Added

- **Survey/Blind Run Mode** — discover all authors, qualify by volume/span/frequency, run full pipeline on every qualified author, rank by composite AI adoption score. Natural control cohort identified automatically from authors with no signal. New `forensics survey` CLI command with `--dry-run`, `--resume`, `--skip-scrape` flags.
- **Interactive TUI Setup Wizard** — 5-screen `textual` wizard (dependency check, author discovery, config generation, preflight validation, pipeline launch). Available via `forensics setup` or `forensics-setup` entry point. Optional `tui` extra dependency.
- **Preflight & Runtime Hardening** — comprehensive preflight module checking Python version, spaCy model, sentence-transformers, Quarto, Ollama, disk space, placeholder authors. Preflight runs at pipeline start. Early-article peer set minimum threshold (5 peers) for self-similarity. Configurable simhash dedup threshold. Rich progress bars for feature extraction and survey runs.
- **Calibration Suite** — synthetic corpus builder (splice AI articles at known date), calibration trial runner, sensitivity/specificity/precision/F1 metrics, date accuracy measurement. New `forensics calibrate` CLI command.
- **Pre-Registration Locking** — `forensics lock-preregistration` snapshots analysis thresholds with SHA256 tamper detection. Analysis pipeline warns if thresholds changed after lock.
- **Permutation-Based Significance** — 1000-iteration permutation test for convergence scores, providing empirical p-values robust to multiple comparisons.
- **Report Overhaul** — survey dashboard notebook, calibration results notebook, per-author parameterized drill-downs, evidence chain narrative generator.
- **Operational QoL** — `forensics validate` (config + endpoint verification), `forensics export` (DuckDB single-file export), checkpoint/resume for survey runs.
- **New modules:** `survey/`, `calibration/`, `tui/`, `preflight.py`, `preregistration.py`, `analysis/permutation.py`, `reporting/narrative.py`, `cli/survey.py`, `cli/calibrate.py`
- **New config section:** `[survey]` with qualification criteria
- **18 new test files/sections** covering all new modules
