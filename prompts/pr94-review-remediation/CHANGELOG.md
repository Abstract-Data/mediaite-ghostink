# Changelog — pr94-review-remediation

## v0.1.0 — 2026-04-26

- **Model:** claude-opus-4-7
- **Status:** active
- **Summary:** Initial remediation prompt covering all 19 items raised in the code review of PR #94 (`notion-review-refactor-run10`). Five CRITICAL items (worker-exception swallowing in `_run_isolated_author_jobs`, non-atomic `merge_parquet_metadata`, per-author empty-filter fallback bug, NFKC simhash migration, incomplete `_sync_patchable_globals` propagation), six HIGH items (orchestrator runner dedup, comparison helper extract, runner docstring cleanup, BH tie stability, single-author cross-author column, `detect_pelt` caller audit), six MEDIUM testing-gap items (E2E in CI, scraper resilience test rewrite, E2E signal assertions, settings cache leak, simhash generator test, BH numeric assertion), two LOW items (HTML fuzz semantic invariant, AI-marker strategy expansion). Includes pre-flight, verification protocol, out-of-scope list, and a definition-of-done checklist.
- **Eval impact:** not yet measured — will be tracked against `uv run pytest tests/ -v --cov=src` baseline captured at execution time.
