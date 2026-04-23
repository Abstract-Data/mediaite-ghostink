# Changelog — Phase 14: Review Remediation (Run 6)

## [0.1.0] — 2026-04-22

**Model:** claude-opus-4-7
**Status:** active

### Added

- 11-phase (A–K) implementation plan covering the 6th-run review pair
  (Notion pages `34b7d7f562988156b81dc139424bd228` + `34b7d7f5629881c3beabd04580e3a63d`).
- **Phase A — Safety quick wins:** `PRAGMA foreign_keys=ON`, spaCy model alignment,
  narrowed CLI exceptions, `run_ai_baseline_command` relocated to `forensics.cli.baseline`.
- **Phase B — Shared helpers:** `write_json_artifact` (11+ migrated sites),
  velocity helpers, `MonthKey` NewType + `iter_months_in_window`.
- **Phase C — Cross-stage coupling:** `AnalysisArtifactPaths` + `resolve_author_rows`
  relocated to `forensics.paths`; analysis modules kept as re-export shims.
- **Phase D — Security:** `_validated_parquet_pattern` across DuckDB call sites.
- **Phase E — Feature count:** `count_scalar_features()` derived from the feature
  model registry replaces the hardcoded `_TOTAL_SCALAR_FEATURES = 35`.
- **Phase F — Complexity:** `_load_embedding_row` → `_load_npy_embedding` +
  `_load_packed_batch`; `compute_convergence_scores` → `ConvergenceInput` +
  `_score_single_window` + `_run_permutation_test`; `_fetch_one_article_html` →
  three `_handle_*` branches; `detect_bocpd` → `_bocpd_init_prior` +
  `_bocpd_step`.
- **Phase G — Data structures:** `DriftPipelineResult` dataclass, frozen
  `Article` with `with_updates(**kwargs)`.
- **Phase H — Repository + streaming:** `iter_articles_by_author`, `scan_features`
  LazyFrame API, Repository partition banner comments.
- **Phase I — Polish:** dispatch-dict for `_run_scrape_mode`, C901 ignore lifted
  for convergence.py, remaining entries annotated with issue IDs.
- **Phase J — Tests:** 8 new unit test modules; coverage 65 → 66.59%.
- **Phase K — Docs:** this prompt family plus HANDOFF update.
