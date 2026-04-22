---
name: report_changes_implementation
overview: Implement all findings from the Apr 21 code review and refactoring reports in a single, ordered roadmap that preserves issue traceability and verification gates. The plan consolidates overlapping recommendations, sequences low-risk quick wins before structural refactors, and uses issue-ID-prefixed task titles for execution tracking.
todos:
  - id: RF-DEAD-001_legacy-cli-removal
    content: "[PARALLEL | WAVE-1] RF-DEAD-001 Legacy CLI cleanup: ensure argparse-era src/forensics/cli.py is removed and all references/tests/docs point to src/forensics/cli/ package only."
    status: completed
  - id: RF-DEAD-002_rf-dead-004_dead-code-hygiene
    content: "[WAIT | WAVE-1B after RF-DEAD-001] RF-DEAD-002/RF-DEAD-004 dead code hygiene: remove deprecated scrape alias and audit/remove unused utils/charts.py if truly unused."
    status: in_progress
  - id: P3-DOC-001_P3-STYLE-001_docs-typing-hygiene
    content: "[PARALLEL | WAVE-1] P3-DOC-001/P3-STYLE-001 docs and typing pass: update ARCHITECTURE.md CLI path references and normalize missing CLI helper return annotations."
    status: completed
  - id: P1-SEC-001_exception-narrowing
    content: "[PARALLEL | WAVE-1] P1-SEC-001 exception-safety hardening: replace broad feature extraction exception catch with explicit expected exception set and keep failure accounting behavior."
    status: completed
  - id: RF-DRY-005_RF-SMELL-006_RF-SMELL-001_local-dry-smells
    content: "[PARALLEL | WAVE-1] RF-DRY-005/RF-SMELL-006/RF-SMELL-001 low-risk DRY refactors: deduplicate readability NaN dict, device resolution helper, and Author row mapping helper in repository."
    status: completed
  - id: P3-PERF-002_comparison-load-optimization
    content: "[PARALLEL | WAVE-1] P3-PERF-002 comparison read optimization: ensure feature frame is loaded once per run path and reused."
    status: completed
  - id: P1-TEST-001_coverage-omissions-removal
    content: "[WAIT | WAVE-6 after P2-TEST-002 + P1-TEST-001_feature-parquet-tests] P1-TEST-001 coverage honesty: remove omissions for implemented pipeline/features/storage modules in pyproject coverage config."
    status: pending
  - id: P2-TEST-002_duckdb-integration-tests
    content: "[WAIT | WAVE-5 after RF-DRY-001 + RF-ARCH-001] P2-TEST-002 DuckDB integration testing: add correctness tests with temp SQLite + Parquet fixtures for rolling and monthly stats queries."
    status: pending
  - id: P1-TEST-001_feature-parquet-tests
    content: "[WAIT | WAVE-5 after P2-PERF-001] P1-TEST-001 targeted tests: add tests for features pipeline edge cases and parquet read/write/error paths currently under-tested."
    status: pending
  - id: RF-DRY-001_repository-initdb-dedup
    content: "[PARALLEL | WAVE-2] RF-DRY-001 repository lifecycle simplification: remove redundant init_db calls preceding Repository context usage and keep schema migration behavior centralized."
    status: pending
  - id: RF-DRY-003_RF-DRY-004_P2-ARCH-002_analysis-shared-loaders
    content: "[PARALLEL | WAVE-2] RF-DRY-003/RF-DRY-004/P2-ARCH-002 analysis loader dedup: centralize overlap and author feature-frame loading helpers in analysis/utils and replace deferred imports."
    status: pending
  - id: RF-ARCH-001_provenance-repository-alignment
    content: "[WAIT | WAVE-3 after RF-DRY-001] RF-ARCH-001 architecture consistency: route provenance read queries through repository-compatible connection path/settings."
    status: pending
  - id: RF-CPLX-001_P2-MAINT-001_orchestrator-decompose
    content: "[WAIT | WAVE-3 after RF-DRY-003/RF-DRY-004/P2-ARCH-002] RF-CPLX-001/P2-MAINT-001 orchestrator decomposition: split run_full_analysis into clear per-author/comparison/artifact helpers while preserving outputs."
    status: pending
  - id: RF-CPLX-002_comparison-decompose
    content: "[WAIT | WAVE-3 after P3-PERF-002 + RF-DRY-003/RF-DRY-004/P2-ARCH-002] RF-CPLX-002 comparison decomposition: extract control and target processing helpers from compare_target_to_controls for readability/testability."
    status: pending
  - id: RF-CPLX-003_fetcher-nesting-reduction
    content: "[PARALLEL | WAVE-3] RF-CPLX-003 fetcher complexity reduction: promote nested async worker to module scope with explicit state passing and simpler concurrency flow."
    status: pending
  - id: RF-SMELL-003_RF-SMELL-004_RF-SMELL-005_parameter-objects
    content: "[WAIT | WAVE-4 after RF-CPLX-001 + RF-CPLX-002] RF-SMELL-003/RF-SMELL-004/RF-SMELL-005 parameter cohesion: introduce context/option dataclasses to replace long signatures and repeated path/settings clumps incrementally."
    status: pending
  - id: RF-SMELL-002_model-cache-abstraction
    content: "[WAIT | WAVE-4 after RF-DRY-005/RF-SMELL-006/RF-SMELL-001] RF-SMELL-002 shared model cache: add reusable cache utility and migrate embeddings/probability/binoculars caching to it."
    status: pending
  - id: P2-PERF-001_embedding-storage-batching
    content: "[WAIT | WAVE-5 after RF-SMELL-003/RF-SMELL-004/RF-SMELL-005] P2-PERF-001 embedding storage scalability: replace per-article .npy write pattern with batched format and backward-compatible read support."
    status: pending
  - id: FULL-VERIFY_report-acceptance-gates
    content: "[WAIT | FINAL-GATE after all tasks] FULL-VERIFY end-to-end validation: run lint/tests/coverage and targeted CLI smoke checks, then confirm all report issue IDs are addressed in final checklist."
    status: pending
isProject: false
---

# Implement Apr 21 Reports End-to-End

## Scope Source
- Code Review Report: [Apr 21, 2026 mediaite-ghostink Code Review Report](https://www.notion.so/abstractdata/Apr-21-2026-mediaite-ghostink-Code-Review-Report-34a7d7f5629881c69ec8f320dca3378d?source=copy_link)
- Refactoring Report: [Apr 21, 2026 mediaite-ghostink Refactoring Analysis Report](https://www.notion.so/abstractdata/Apr-21-2026-mediaite-ghostink-Refactoring-Analysis-Report-34a7d7f562988131bd90ce3b00d5deb0?source=copy_link)

## Primary Files Touched
- CLI and docs: [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/cli/scrape.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/cli/scrape.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/docs/ARCHITECTURE.md`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/docs/ARCHITECTURE.md)
- Analysis stack: [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/orchestrator.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/orchestrator.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/comparison.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/comparison.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/convergence.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/convergence.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/utils.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/analysis/utils.py)
- Features and storage: [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/features/pipeline.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/features/pipeline.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/storage/repository.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/storage/repository.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/storage/duckdb_queries.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/storage/duckdb_queries.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/storage/parquet.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/src/forensics/storage/parquet.py)
- Tests/config: [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/tests/test_analysis.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/tests/test_analysis.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/tests/test_scraper.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/tests/test_scraper.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/tests/integration/test_cli.py`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/tests/integration/test_cli.py), [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/pyproject.toml`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/pyproject.toml)

## Consolidation Rules
- Treat overlapping findings as single implementation streams:
  - Long-function decomposition combines `P2-MAINT-001` + `RF-CPLX-001/002/003`.
  - Shared analysis loader/dedup combines `P2-ARCH-002` + `RF-DRY-003/004`.
  - Coverage and test improvements combine `P1-TEST-001` + `P2-TEST-002`.
- Preserve traceability by keeping issue IDs in task titles and commit/PR checklist entries.

## Execution Phases

### Phase 0 — Baseline and Safety Gates
- Snapshot current metrics (`ruff`, tests, coverage) and preserve a before/after benchmark.
- Confirm no behavior drift by running existing CLI integration paths before refactors.
- Keep each issue family on focused commits to simplify rollback.

### Phase 1 — Critical/Quick-Win Cleanup (No architectural redesign)
- Complete dead-code and docs/annotation hygiene items first:
  - `RF-DEAD-001`, `RF-DEAD-002`, `RF-DEAD-004`
  - `P3-DOC-001`, `P3-STYLE-001`
  - `RF-DRY-005`, `RF-SMELL-006`, `RF-SMELL-001`, `P1-SEC-001`, `P3-PERF-002`
- Verify parity with targeted unit/integration tests and lint.

### Phase 2 — Coverage Honesty + Storage Query Validation
- Remove outdated coverage omissions (`P1-TEST-001`) in [`/Users/johneakin/PyCharmProjects/mediaite-ghostink/pyproject.toml`](/Users/johneakin/PyCharmProjects/mediaite-ghostink/pyproject.toml).
- Add missing tests for:
  - Feature extraction pipeline error/edge paths
  - Parquet utility read/write/error paths
  - DuckDB cross-store queries (`P2-TEST-002`)
- Add/adjust fixtures for temporary SQLite + Parquet integration datasets.

### Phase 3 — DRY and Repository Pattern Consolidation
- Remove redundant `init_db()` pre-calls when immediately entering `Repository` contexts (`RF-DRY-001`).
- Standardize author resolution/loading helpers and module-level imports (`RF-DRY-004`, `P2-ARCH-002`).
- Move duplicate interval overlap logic to shared utility (`RF-DRY-003`).
- Align provenance DB access with repository connection policy (`RF-ARCH-001`).

### Phase 4 — Function Decomposition and Parameter Cohesion
- Refactor large orchestration functions into named helpers (`RF-CPLX-001`, `RF-CPLX-002`, `P2-MAINT-001`).
- Flatten nested async closure in scraper fetch flow (`RF-CPLX-003`).
- Introduce parameter objects/context dataclasses for long signatures and data clumps (`RF-SMELL-003`, `RF-SMELL-004`, `RF-SMELL-005`) while preserving external CLI behavior.

### Phase 5 — Model Cache and Embedding Storage Strategy
- Implement shared model-cache abstraction and migrate modules (`RF-SMELL-002`).
- Implement batched embedding storage strategy (`P2-PERF-001`) with backward-compatible read path/migration handling.
- Add regression tests and a small benchmark for embedding load/write performance.

### Phase 6 — Validation and Ship Criteria
- Run full verification suite:
  - `uv run ruff check .`
  - `uv run pytest tests/ -v --cov=src --cov-report=term-missing`
  - Any targeted smoke commands for CLI pipeline stages
- Confirm report acceptance criteria:
  - No dead legacy CLI path
  - No duplicated interval/device helpers
  - Reduced max function size/nesting
  - Coverage reflects implemented modules
  - DuckDB queries functionally tested

## Verification Matrix
- Static quality: Ruff clean, no unused imports/dead aliases.
- Behavioral parity: existing integration CLI tests pass unchanged.
- Data-path safety: DuckDB/Parquet/SQLite integration tests pass.
- Coverage integrity: implemented modules no longer omitted.
- Refactor confidence: focused tests added for all previously untested critical paths.

## Delivery Ordering
- Execute in this order for minimal risk: Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6.
- Open a tracking checklist where each checklist line starts with the report issue ID to satisfy traceability and naming requirements.