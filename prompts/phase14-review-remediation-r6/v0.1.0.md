# Phase 14: Review Remediation (Run 6)

Version: 0.1.0
Status: active
Last Updated: 2026-04-22
Model: claude-opus-4-7

---

## Mission

Implement every actionable finding from the 6th-run Apr 22, 2026 review pair
delivered after Phase 13 closed:

- Code Review Report — https://www.notion.so/34b7d7f562988156b81dc139424bd228
- Refactoring Analysis Report — https://www.notion.so/34b7d7f5629881c3beabd04580e3a63d

Scope: P1/P2/P3 findings from the Code Review (SQL hardening, FK enforcement,
frozen Article, streaming reads, preflight/pipeline spaCy alignment, feature
count registry) and the full RF-* matrix from the Refactoring report (JSON
artifact DRY, velocity DRY, MonthKey type, convergence + fetcher + BOCPD +
embedding-loader decomposition, DriftPipelineResult dataclass, cross-stage
coupling fix).

---

## Approach

11 phases (A–K) executed in order: safety → shared helpers → cross-stage
relocation → security hardening → feature-count decoupling → complexity
reduction → data-structure hygiene → Repository/streaming → polish → tests →
docs. Each phase leaves `uv run ruff check` and `uv run pytest` green.

See the approved plan for the full breakdown:
`~/.claude/plans/review-https-www-notion-so-34b7d7f562988-dynamic-pancake.md`.

---

## Outcome (realised 2026-04-22)

- **Security:** DuckDB Parquet globs routed through `_validated_parquet_pattern`;
  SQLite foreign keys enforced via `PRAGMA foreign_keys=ON`; CLI exception
  catches narrowed to pydantic/tomllib/OSError tuples.
- **DRY:** Shared `write_json_artifact` consolidates 11+ JSON-artifact
  sites across analysis/survey/calibration; velocity helpers
  (`pair_months_with_velocities`, `compute_velocity_acceleration`,
  `describe_velocity_acceleration_pct`) centralise the drift split across
  orchestrator/drift/survey/narrative.
- **Types:** `MonthKey` NewType + `iter_months_in_window` replaces ad-hoc
  month-key parsing in convergence; `DriftPipelineResult` dataclass replaces
  the 6-tuple from `compute_author_drift_pipeline`; Article model frozen
  with `with_updates(**kwargs)`.
- **Complexity:** `compute_convergence_scores` decomposed into
  `ConvergenceInput` + `_score_single_window` + `_run_permutation_test`;
  `_fetch_one_article_html` split into `_handle_http_failure` /
  `_handle_off_domain` / `_handle_success`; `detect_bocpd` factored into
  `_bocpd_init_prior` + `_bocpd_step`; `_load_embedding_row` dispatched to
  `_load_npy_embedding` / `_load_packed_batch`. C901 ignore lifted for
  convergence.py.
- **Architecture:** `AnalysisArtifactPaths` + cross-stage utilities moved to
  `forensics.paths`; old locations kept as re-export shims. Repository
  partitioned with section banners + streaming `iter_articles_by_author`.
- **Coverage:** Lifted from 65 → 66 with 8 new unit test modules covering
  json_io, velocity, monthkeys, duckdb pattern validation, frozen Article,
  FK pragma, feature count registry, and repository streaming.

---

## Definition of Done

- [x] Every P1/P2/P3 finding landed or annotated in-code.
- [x] Every RF-* finding landed or annotated in-code.
- [x] `uv run pytest tests/ -v` passes at 66.59% coverage (≥ fail_under=66).
- [x] `uv run ruff check .` passes.
- [x] `uv run ruff format --check .` passes.
- [x] HANDOFF.md updated with completion block.
- [ ] Follow-up: re-run python-project-review skill after the 7th external
      audit to validate score uplift projection (Security +1, Testing +2,
      Architecture +1, Maintainability +1).
