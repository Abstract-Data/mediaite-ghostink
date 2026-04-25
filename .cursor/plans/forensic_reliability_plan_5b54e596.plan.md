---
name: Forensic Reliability Plan
overview: Implement the full punch list as a phased forensic reliability upgrade, starting with broken evidence-chain behavior and then adding conservative methodology gates, sensitivity outputs, and reporting surfaces. The plan assumes hard failures for missing preregistration and mixed config hashes, effect-size gated change-points, and pooled bylines treated as content streams unless individual authorship can be recovered confidently.
todos:
  - id: artifact-inventory
    content: Inventory current analysis, baseline, feature, embedding, and legacy DB artifacts.
    status: completed
  - id: tier0-repairs
    content: Repair AI baseline loading, NaN feature comparisons, legacy DB cleanup, and config-hash report gates.
    status: completed
  - id: methodology-gates
    content: Calibrate AI markers, preregister minimal tests, and gate change-points by effect size.
    status: completed
  - id: sensitivity-design
    content: Add section-residualized sensitivity outputs, shared-byline handling, era classification, and AB-pass documentation/tests.
    status: completed
  - id: reporting-verification
    content: Generate per-author evidence pages, rerun the pipeline, validate, and update handoff documentation.
    status: in_progress
isProject: false
---

# Forensic Reliability Implementation Plan

## Context And Constraints

- Applicable AGENTS rules: preserve `scrape -> extract -> analyze -> report`, use `uv run` for all Python commands, keep storage writes under `data/`, prefer incremental fixes, add tests for behavior changes, update `HANDOFF.md` before completion.
- Relevant GUARDRAILS Signs: embedding model version mismatch, Parquet schema evolution, hand-built data paths, inlined feature frame loading, do not mix pre/post Phase-15 artifacts in one report.
- Scope: read/write `src/`, `tests/`, `docs/`, `prompts/`, and `data/` artifacts needed by the plan. Off-limits: `.env`, secrets, provider swaps, infrastructure, and any redesign of stage boundaries.
- GitNexus rule for execution: before editing any touched function/class, run upstream impact analysis for the symbol and report blast radius. Before commit, run staged change detection.
- Conservative defaults selected: hard-fail report/analyze gates when evidence-chain prerequisites are missing, use `effect_size_threshold = 0.2` for change-point counting, and treat `mediaite-staff` / `mediaite` as pooled content streams rather than individuals.

## Phase 0: Reproduce And Inventory Current Artifacts

Task ID: TASK-1
Title: Artifact inventory and failing evidence map
Exec mode: parallel
Model: claude-sonnet-4-6
Model rationale: Default multi-step reasoning model for tracing artifact contracts without over-reading the whole repo.
Est. tokens: ~50K
Risk: LOW

- Inventory current `data/analysis/*_result.json`, `data/analysis/run_metadata.json`, `data/ai_baseline/`, `data/embeddings/`, `data/features/`, and `data/forensics.db`.
- Confirm which authors have null `drift_scores.ai_baseline_similarity`, stale or mixed `config_hash`, and NaN comparison fields.
- Produce a short diagnostic artifact under `data/analysis/diagnostics/` so later phases have a before/after baseline.
- Use existing path helpers from [`src/forensics/paths.py`](src/forensics/paths.py), not ad hoc data paths.

## Tier 0: Fix Broken Pipeline Behavior

Task ID: TASK-2
Title: Repair AI baseline drift loading
Exec mode: sequential[after: TASK-1]
Model: claude-sonnet-4-6
Model rationale: Requires careful tracing across baseline generation, drift analysis, and existing tests.
Est. tokens: ~50K
Risk: MEDIUM

- Fix the likely path contract mismatch between baseline generation in [`src/forensics/baseline/orchestrator.py`](src/forensics/baseline/orchestrator.py) and AI baseline loading in [`src/forensics/analysis/drift.py`](src/forensics/analysis/drift.py).
- Current loader reads `data/ai_baseline/{slug}/embeddings/*.npy`; generator documentation indicates nested model/mode/temperature directories. Make the loader manifest-aware and recursive while validating vector dimensionality against the pinned 384-dim embedding model.
- Add tests in [`tests/test_baseline.py`](tests/test_baseline.py) and [`tests/test_analysis_drift_pipeline.py`](tests/test_analysis_drift_pipeline.py) that prove nested generated baselines populate `ai_baseline_similarity` and missing baselines remain explicit `None`.
- Add a report/analyze diagnostic that fails loudly when a configured author has drift artifacts but no AI baseline vectors after baseline generation was requested.

Task ID: TASK-3
Title: Fix NaN feature comparisons
Exec mode: sequential[after: TASK-1]
Model: claude-sonnet-4-6
Model rationale: Small but correctness-sensitive numerical path across extraction and comparison.
Est. tokens: <10K
Risk: MEDIUM

- Add focused extractor regression tests for `hedging_frequency`, `first_person_ratio`, `subordinate_clause_depth`, and `paragraph_length_variance` using simple fixture text in [`tests/test_features.py`](tests/test_features.py).
- Fix finite-value handling in [`src/forensics/analysis/comparison.py`](src/forensics/analysis/comparison.py): `drop_nulls()` does not remove `NaN`, so t-tests should explicitly filter to finite values before computing statistics and means.
- Add a feature coverage diagnostic that records all-zero, all-null, and all-NaN columns per author before comparison output is trusted.
- If an extractor itself is defective, keep the fix inside the existing extractor modules: [`src/forensics/features/content.py`](src/forensics/features/content.py), [`src/forensics/features/structural.py`](src/forensics/features/structural.py), and [`src/forensics/features/lexical.py`](src/forensics/features/lexical.py).

Task ID: TASK-4
Title: Remove stale legacy DB artifact
Exec mode: sequential[after: TASK-1]
Model: claude-haiku-4-5
Model rationale: Low-complexity cleanup once the artifact inventory proves it is unused.
Est. tokens: <10K
Risk: LOW

- Verify no code path references `data/forensics.db`; the current architecture contract uses `data/articles.db`.
- Delete `data/forensics.db` if it is confirmed to be a zero-byte legacy artifact.
- Add a preflight/report diagnostic so future zero-byte legacy DB artifacts are flagged instead of silently confusing operators.

Task ID: TASK-5
Title: Enforce result config consistency
Exec mode: sequential[after: TASK-1]
Model: claude-sonnet-4-6
Model rationale: Needs care because the repo currently has separate raw-config and analysis-config hashes.
Est. tokens: ~50K
Risk: HIGH

- Add a validation helper that computes the current analysis result hash with `compute_model_config_hash(settings.analysis, length=16, round_trip=True)` and compares it to each `*_result.json` `config_hash`.
- Wire the helper into report prerequisites in [`src/forensics/reporting/__init__.py`](src/forensics/reporting/__init__.py) so mixed author artifacts hard-fail before Quarto renders.
- Wire the same validation into compare-only analysis in [`src/forensics/analysis/orchestrator.py`](src/forensics/analysis/orchestrator.py) so stale files are not reused for control comparisons.
- Preserve `run_metadata.json` raw TOML hash separately, but document the two-hash contract in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- After fixes, rerun all authors so per-author results share the same current analysis hash.

## Tier 1: Conservative Methodology Gates

Task ID: TASK-6
Title: Calibrate AI marker feature
Exec mode: sequential[after: TASK-3]
Model: claude-sonnet-4-6
Model rationale: Requires balancing prompt artifact versioning, feature extraction, and measured calibration.
Est. tokens: ~50K
Risk: MEDIUM

- Build a labeled calibration set: 50 GPT-4o synthetic control articles using the existing baseline generation path and 50 pre-Nov-2022 human articles from the corpus.
- Store calibration metadata under `data/calibration/` and keep generated text/data under `data/` only.
- Version the marker list as an immutable prompt artifact under `prompts/ai-marker-frequency/v0.1.0.md`, with `current.md`, `versions.json`, and `CHANGELOG.md` following [`prompts/README.md`](prompts/README.md).
- Update `ai_marker_frequency` in [`src/forensics/features/lexical.py`](src/forensics/features/lexical.py) only if calibration shows the current list fails to discriminate.
- Add tests that pin the marker-list version and calibration scorer behavior without depending on live LLM calls.

Task ID: TASK-7
Title: Preregister minimal test battery
Exec mode: sequential[after: TASK-6]
Model: claude-sonnet-4-6
Model rationale: Methodology change with pipeline gates and statistical tests.
Est. tokens: ~50K
Risk: HIGH

- Define a minimal confirmatory battery in [`src/forensics/preregistration.py`](src/forensics/preregistration.py): six preregistered features, two tests per feature, split at Nov 2022, with global multiple-comparison correction across authors rather than only within author.
- Set `analysis.effect_size_threshold` default to `0.2` in [`src/forensics/config/settings.py`](src/forensics/config/settings.py) and include it in preregistration lock content.
- Change `verify_preregistration` usage in [`src/forensics/cli/analyze.py`](src/forensics/cli/analyze.py) from soft metadata to a hard fail for `missing` or `mismatch` unless an explicit exploratory override is added and recorded.
- Add a checked-in preregistration template or generated lock under `data/preregistration/` once thresholds are finalized.
- Add tests in [`tests/test_preregistration.py`](tests/test_preregistration.py), [`tests/unit/test_statistics.py`](tests/unit/test_statistics.py), and CLI integration coverage.

Task ID: TASK-8
Title: Gate change-points by effect size
Exec mode: sequential[after: TASK-7]
Model: claude-sonnet-4-6
Model rationale: Correctness-sensitive change in what counts as evidence and feeds convergence.
Est. tokens: ~50K
Risk: HIGH

- Add a helper that filters `ChangePoint` records by both `confidence >= 0.9` and `abs(effect_size_cohens_d) >= settings.analysis.effect_size_threshold` before events are counted or passed to convergence.
- Apply the helper in [`src/forensics/analysis/orchestrator.py`](src/forensics/analysis/orchestrator.py) before convergence scoring, hypothesis tests, result assembly, and changepoint JSON writes.
- Ensure standalone change-point analysis and compare-only fallback paths in [`src/forensics/analysis/comparison.py`](src/forensics/analysis/comparison.py) use the same gated event list.
- Add tests that reproduce a high-confidence / tiny-effect event and prove it is excluded.

Task ID: TASK-9
Title: Add section-residualized sensitivity runs
Exec mode: sequential[after: TASK-8]
Model: claude-sonnet-4-6
Model rationale: Uses existing Phase 15 residualization knobs but needs careful artifact separation.
Est. tokens: ~50K
Risk: MEDIUM

- Add a sensitivity analysis path for flagged authors that reruns analysis with `section_residualize_features=True` without overwriting the primary preregistered artifacts.
- Write sensitivity outputs under a separate analysis subdirectory or filename suffix, for example `data/analysis/sensitivity/section_residualized/`.
- Compare primary vs residualized change-point counts and downgrade evidence in reports if counts collapse.
- Use URL-derived section tags per [`docs/GUARDRAILS.md`](docs/GUARDRAILS.md), not sparse article metadata.

## Tier 2: Design And Interpretability Improvements

Task ID: TASK-10
Title: Treat shared bylines as pooled streams
Exec mode: sequential[after: TASK-5]
Model: claude-sonnet-4-6
Model rationale: Touches author identity semantics and reporting labels without redesigning the scraper.
Est. tokens: ~50K
Risk: HIGH

- Implement or restore the shared-byline classifier referenced by the existing migration, using conservative slug/name matching for `mediaite-staff`, `mediaite`, and similar house accounts.
- Prefer reporting shared bylines as “pooled content stream” rather than splitting authorship in the first implementation pass.
- Wire shared-byline status into survey qualification and report labels using existing settings such as `survey.exclude_shared_bylines` in [`src/forensics/config/settings.py`](src/forensics/config/settings.py).
- Add tests for individual authors vs shared bylines, including the CLI escape hatch to include shared bylines when explicitly requested.

Task ID: TASK-11
Title: Add era classification output
Exec mode: sequential[after: TASK-8]
Model: claude-sonnet-4-6
Model rationale: Additive data-model output with date bucketing and reporting impact.
Est. tokens: ~50K
Risk: MEDIUM

- Add `era_classification` to [`src/forensics/models/analysis.py`](src/forensics/models/analysis.py) as an additive field on `AnalysisResult`.
- Bucket high-confidence, effect-size-gated AI-marker change-points into pre-Nov-2022, Nov-2022 to Mar-2023, Mar-2023 to Dec-2023, and post-Dec-2023.
- Populate the field in [`src/forensics/analysis/orchestrator.py`](src/forensics/analysis/orchestrator.py) and surface it in narrative/reporting.
- Add tests with fixed timestamps to pin boundary behavior.

Task ID: TASK-12
Title: Document and test AB-pass convergence
Exec mode: sequential[after: TASK-8]
Model: claude-haiku-4-5
Model rationale: Focused documentation and unit-test work after behavior is clear.
Est. tokens: <10K
Risk: LOW

- Document the exact AB-pass rule from [`src/forensics/analysis/convergence.py`](src/forensics/analysis/convergence.py): Pipeline A score > 0.5 and Pipeline B score > 0.5 can pass even when ratio gating does not.
- Justify threshold constants and AI-curve behavior in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- Add unit tests in [`tests/unit/test_convergence.py`](tests/unit/test_convergence.py) that pin `passes_ab`, `passes_ratio`, and failure cases independently.

## Tier 3: Reporting Improvements

Task ID: TASK-13
Title: Generate per-author evidence pages
Exec mode: sequential[after: TASK-11]
Model: claude-sonnet-4-6
Model rationale: Crosses report orchestration, notebook rendering, and final determination flow.
Est. tokens: ~50K
Risk: MEDIUM

- Surface existing parameterized notebooks (`05`, `06`, `07`, `09`, `11`) through a per-author report entry point rather than leaving them as manual renders.
- Add a report option or manifest-driven render path in [`src/forensics/reporting/__init__.py`](src/forensics/reporting/__init__.py) that creates one page per Tier-1 / Tier-2 author.
- Include each author’s change-point timeline, significant preregistered tests with confidence intervals, AI-baseline drift status, section-residualization sensitivity summary, era classification, and representative before/after URLs.
- Keep notebooks as the presentation layer and use Python helpers for deterministic data assembly so tests can cover the report data without requiring Quarto.

Task ID: TASK-14
Title: Rerun and verify full evidence chain
Exec mode: sequential[after: TASK-2,TASK-3,TASK-4,TASK-5,TASK-6,TASK-7,TASK-8,TASK-9,TASK-10,TASK-11,TASK-12,TASK-13]
Model: claude-sonnet-4-6
Model rationale: Final validation requires coordinating pipeline commands and interpreting outputs.
Est. tokens: ~50K
Risk: MEDIUM

- Refresh baseline, extraction, analysis, comparison, sensitivity, and report artifacts in the correct stage order.
- Confirm every configured author has current-hash result artifacts, populated AI-baseline similarity when baseline artifacts exist, finite comparison metrics, and no mixed config hashes.
- Append the required completion block to [`HANDOFF.md`](HANDOFF.md), including files changed, decisions, unresolved questions, and verification command summaries.
- Update [`docs/RUNBOOK.md`](docs/RUNBOOK.md) only for new operational commands or recurring error fixes discovered during execution.
- Update [`docs/GUARDRAILS.md`](docs/GUARDRAILS.md) only if execution reveals a repeated failure pattern.

## Validation Commands

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest tests/ -v`
- Targeted tests during implementation: `uv run pytest tests/test_analysis_drift_pipeline.py tests/test_baseline.py tests/test_features.py tests/test_preregistration.py tests/unit/test_convergence.py -v`
- Pipeline verification after approval and implementation: `uv run forensics analyze --ai-baseline`, `uv run forensics analyze`, and `uv run forensics report --verify` as applicable to the final CLI contract.

## Expected Acceptance Criteria

- `ai_baseline_similarity` is non-null for authors with valid generated AI baselines and remains explicitly null only when baseline artifacts are absent.
- The listed feature comparisons no longer emit NaN statistics because non-finite values are filtered and extractor outputs are regression-tested.
- `data/forensics.db` is removed if confirmed unused, and `data/articles.db` remains the canonical SQLite store.
- Reports hard-fail on mixed per-author `config_hash` values and on missing/mismatched preregistration for confirmatory runs.
- Change-points counted as evidence satisfy both confidence and effect-size gates.
- Shared bylines are labeled as pooled content streams, not individual authors.
- Per-author pages expose the evidence needed to audit each determination.