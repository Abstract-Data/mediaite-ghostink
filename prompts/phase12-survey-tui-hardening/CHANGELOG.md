# Changelog — Phase 12: Survey Mode, Interactive TUI, Runtime Hardening & Calibration

## [0.2.0] — 2026-04-22

**Model:** claude-opus-4-6
**Status:** pending

### Fixed (codebase alignment audit — 17 corrections)

- **Survey orchestrator** — replaced non-existent `run_analysis_for_author` import with actual `run_full_analysis` from `forensics.analysis.orchestrator`; use `AnalysisArtifactPaths.from_project()` factory instead of incorrect positional constructor
- **Repository `all_authors()`** — now uses `self._require_conn()` guard and `_author_row_to_model()` helper per ADR-001 context manager pattern
- **Qualification filter** — `repo.articles_for_author()` → `repo.get_articles_by_author()` (actual method name); simplified `word_count` truthiness check
- **Survey CLI** — `from forensics.cli.scrape import _dispatch` → `dispatch_scrape` (actual export); added `all_authors=False` kwarg to match real signature
- **Dedup threshold** — replaced fictional `deduplicate_articles(db_path, threshold=3)` with note that `hamming_threshold` kwarg already exists; instructions now say "wire config value to existing kwarg" instead of "change function signature"
- **Content self-similarity** — replaced fictional `compute_self_similarity` function with actual `_self_similarity(current, peers)` using `_self_similarity_cached`; return type changed to `float | None`
- **Pre-registration locking** — replaced `getattr(settings.analysis, ...)` with direct attribute access (`settings.analysis.effect_size_threshold`, etc.) since fields are defined in `AnalysisConfig`
- **Feature count** — `_count_total_features()` corrected from 38 to 35 with detailed scalar/dict field breakdown
- **`extract_all_features` signature** — added missing `project_root: Path | None = None` keyword argument
- **Preflight pipeline integration** — added `PipelineContext.resolve().record_audit()` reference and placement note
- **SurveyConfig field** — changed from bare default to `Field(default_factory=SurveyConfig)` with explicit field ordering context
- **Notebook numbering** — `00_survey_dashboard` → `10_survey_dashboard`, `03a_calibration` → `11_calibration` to avoid conflicts with existing 00–09 notebooks
- **Dependencies section** — removed unnecessary `rich` pin (already transitive via typer); clarified `tui` extra format
- **Baseline config note** — documented that shipped `config.toml` uses `models = ["llama3.2:latest"]` vs `BaselineConfig` three-model default

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
