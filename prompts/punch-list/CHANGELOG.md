# Changelog — Forensic Punch List

## [0.1.0] — 2026-04-26

**Model:** claude-sonnet-4-6
**Status:** active

### Added

- Initial 92-item punch list covering 9 categories (A–I): methodology/statistical/conceptual (M-01–M-23), code quality (C-01–C-12), data/corpus (D-01–D-10), configuration/infrastructure (I-01–I-06), documentation/reporting (R-01–R-09), reproducibility/provenance (P-01–P-05), logging/observability (L-01–L-06), testing gaps (T-01–T-07), miscellaneous/nits (N-01–N-06).
- Five critical-severity items identified: M-01 (preregistration lock unfilled), M-02 (ai_baseline_similarity null for all authors), M-03 (comparison_report.json empty), M-04 (all authors role="control"), M-05 (post-hoc threshold changes), R-01 (HIGH confidence verdict contradicts exploratory status).
- "Top 5 to Fix Before Any Public Claim" section.
- Short-code IDs for all issues enabling cross-reference with implementation-plan.

### Sources

- Full codebase review of mediaite-ghostink Phase 16 (post-adversarial-review-remediation).
- Findings based on reading: `src/forensics/analysis/`, `src/forensics/features/`, `src/forensics/scraper/`, `src/forensics/utils/`, `config.toml`, `data/reports/AI_USAGE_FINDINGS.md`, `data/analysis/run_metadata.json`, `data/preregistration/preregistration_lock.json`, `data/adversarial_review_2026-04-23.md`.

### Phase 0 closure (2026-04-26)

Operational + narrative work aligned with [implementation-plan Phase 0](../implementation-plan/current.md). Original M/R rows in `current.md` remain as historical audit text; this table is the remediation index.

| ID | Resolution |
|----|--------------|
| M-01 | `uv run forensics lock-preregistration` → `data/preregistration/preregistration_lock.json` with `locked_at`, `analysis`, `content_hash`. |
| M-02 | `uv run python scripts/seed_phase0_ai_baseline_stubs.py` → stub `.npy` under `data/ai_baseline/...` (gitignored) + `uv run forensics analyze --drift --exploratory --allow-pre-phase16-embeddings` → non-null `ai_baseline_similarity` in `*_drift.json`. Replace with Ollama-backed baseline per `docs/RUNBOOK.md` § Phase 0. |
| M-03 | `uv run forensics analyze --compare` → `data/analysis/comparison_report.json` populated (`targets.colby-hall`, …). |
| M-04 | Verified `config.toml`: exactly one `role = "target"` (`colby-hall`); survey path excludes forbidden slugs per AGENTS. |
| M-05 | Appended Fix-F / Fix-G amendment to `data/preregistration/amendment_phase15.md` (exploratory disclosure). |
| R-01–R-09 | Rewrote `data/reports/AI_USAGE_FINDINGS.md`: exploratory disclosure, table tone, pooled-byline caveat, bigram_entropy as supporting-only, `AI_MARKER_LIST_VERSION` line, per-row A–D column, cross-corpus accuracy, comparison file note. |

### Full-stack closure index (2026-04-26)

Machine-readable **ID → evidence** map for all 92 items (methodology through N-06), including ADR gates (C-06, M-22) and human gates (M-08): [`docs/punch-list-closure-index.md`](../../docs/punch-list-closure-index.md). Phase 0 rows above remain the authoritative table for M-01–M-05 and R-01–R-09 operational closure; the doc extends the same pattern repo-wide.
