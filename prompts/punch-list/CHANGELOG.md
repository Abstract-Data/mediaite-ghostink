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
