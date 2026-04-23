# Changelog — Phase 13: Code Review & Refactoring Remediation

## [1.0.0] — 2026-04-23

**Model:** claude-opus-4-6
**Status:** active
**Breaking:** Yes — complete rewrite based on Run 7 findings. Supersedes v0.1.0.

### Changed

- **Fresh implementation plan** based on Run 7 Code Review and Refactoring Analysis reports. All items from v0.1.0 that were already implemented in Runs 5-6 are removed.
- **27 steps across 7 phases** (A: Quick Wins, B: DRY & API Consolidation, C: Decomposition, D: Model & Type Safety, E: Performance, F: Testing & Coverage, G: Cleanup).
- **No deferrals** — every item from both reports is addressed.

### Added

- **ConvergenceInput API collapse** (B1): highest-impact refactoring — collapses dual 12-param + parameter-object API into single ConvergenceInput parameter with `from_settings()` factory.
- **HypothesisTest freeze** (D1): copy-on-write pattern matching frozen Article model.
- **xxhash migration** (E2): replaces SHA-256 per n-gram in simhash for ~10-50x dedup speedup.
- **LazyFrame return refactor** (E1): `load_feature_frame_sorted` returns LazyFrame for predicate pushdown.
- **DuckDB validation tests** (F1): security-critical path validation functions get dedicated test coverage.
- **Coverage target raised** to 70% (F4).
- **Issue cross-reference tables** mapping every CR and RF issue ID to its prompt step.

### Deprecated

- v0.1.0 — most items already implemented; remaining items superseded by Run 7 findings.

---

## [0.1.0] — 2026-04-22

**Model:** claude-opus-4-6
**Status:** active

### Added

- **20-step implementation plan** addressing all findings from the 5th-run Code Review (P1-PERF-001 through P3-STYLE-002) and Refactoring Analysis (RF-DRY-001 through RF-DC-002).
- **6 phases** with dependency ordering: Quick Wins (A), DRY Extraction (B), Decomposition (C), Testing & Coverage (D), Structural Improvements (E), Cache Fix (F).
- **Critical path items:** BOCPD vectorization (A1), `ensure_repo` context manager (B1), `extract_all_features` decomposition (C1).
- **Testing targets:** Coverage threshold 50→65, new unit tests for convergence, content LDA, and fetcher mutations.
- **Traceability:** Every step maps to a specific Issue ID from the source reports with file paths and line numbers.
- **Risk classification** per AGENTS.md: LOW/MEDIUM/HIGH with mitigation strategies for HIGH-risk steps.
- **Definition of Done** including re-review validation via python-project-review skill.
