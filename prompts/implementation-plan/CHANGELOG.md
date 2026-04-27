# Changelog — Implementation Plan

## [0.1.0] — 2026-04-26

**Model:** claude-sonnet-4-6
**Status:** active

### Added

- 7-phase sequenced implementation plan addressing all 92 items from the forensic punch list (M-01–N-06).
- Phase 0 (blockers): 6 steps covering prerequisites for any public claim — preregistration lock, target author configuration, comparison analysis, AI baseline, Fix-F/G documentation, verdict downgrade.
- Phase 1 (methodology): 13 steps covering forensic integrity improvements — marker list audit, mediaite-staff disaggregation, external controls, cross-author BH correction, PELT rename, BOCPD calibration, contradiction investigation, section sensitivity, sample size floor, autocorrelation documentation, ground truth, drift-only documentation, spot-check reading.
- Phase 2 (data quality): 7 steps covering simhash normalization, UTC datetime enforcement, scraper coverage report, manifest dedup, URL section fix, metadata error handling, word count filter.
- Phase 3 (code quality/reproducibility): 7 steps covering sort determinism, NaN imputation, zero-norm guards, atomic dedup transaction, provenance seeds in config_hash, cross-run hash validation, manifest scan.
- Phase 4 (logging/observability): 4 steps covering convergence component JSON, comparison warning, baseline warning, exploratory stderr warning.
- Phase 5 (testing): 5 steps covering comparison test, sort determinism test, marker FP rate test, config hash invalidation test, dedup atomicity test.
- Phase 6 (infrastructure): 3 steps covering scraper settings in config_hash, adaptive convergence window, embedding dim derivation.
- Phase 7 (nits): 4 steps.
- Dependency graph across all phases.
- Human Decision Checklist with 6 items requiring editorial/legal judgment.
- "First Concrete Next Step" with exact bash commands.

### Sources

- References `prompts/punch-list/current.md` (92 items, IDs M-01 through N-06).
- Exact code locations derived from reading Phase 16 codebase.
