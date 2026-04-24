---
name: unit
description: "Skill for the Unit area of mediaite-ghostink. 222 symbols across 44 files."
---

# Unit

222 symbols | 44 files | Cohesion: 74%

## When to Use

- Working with code in `tests/`
- Understanding how test_convergence_window, test_from_settings_pulls_permutation_knobs_from_analysis, test_from_settings_passes_through_optional_signals work
- Modifying unit-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/unit/test_statistics.py` | _make_test, test_apply_correction_empty_is_noop, test_apply_correction_bonferroni_scales_by_n, test_apply_correction_bonferroni_clips_at_one, test_apply_correction_benjamini_hochberg (+18) |
| `tests/unit/test_duckdb_validation.py` | test_validated_parquet_pattern_accepts_plain_glob, test_validated_parquet_pattern_rejects_empty, test_validated_parquet_pattern_rejects_remote_uris, test_validated_parquet_pattern_rejects_control_chars, test_validated_parquet_pattern_escapes_single_quotes (+7) |
| `tests/unit/test_fetcher_mutations.py` | _make_article, test_persist_and_log_off_domain_branch, test_persist_and_log_skips_when_row_missing, test_persist_and_log_counter_is_shared_across_branches, test_persist_and_log_dispatches_via_asyncio_to_thread (+7) |
| `tests/unit/test_content_lda.py` | test_empty_corpus_returns_nan, test_single_document_corpus_returns_nan, test_two_document_corpus_returns_nan, test_identical_documents_yield_low_entropy, test_corpus_with_no_vocabulary_returns_nan (+6) |
| `tests/unit/test_velocity.py` | test_compute_velocity_acceleration_requires_six_points, test_compute_velocity_acceleration_clamps_to_unit_interval, test_compute_velocity_acceleration_returns_zero_for_zero_early, test_compute_velocity_acceleration_mid_range, test_describe_velocity_acceleration_pct_none_when_undefined (+5) |
| `src/forensics/scraper/fetcher.py` | _resume_skip_fetch, _apply_http_failed_mutation, _apply_off_domain_mutation, _handle_http_failure, _handle_off_domain (+4) |
| `tests/unit/test_json_io.py` | _Sample, test_write_json_artifact_creates_parents, test_write_json_artifact_serialises_single_model, test_write_json_artifact_serialises_list_of_models, test_write_json_artifact_handles_datetime_default_str (+4) |
| `tests/unit/test_crawler_ingest_single_post.py` | _wp_post, test_ingest_single_post_parses_metadata_only_row, test_ingest_single_post_parses_content_when_provided, test_ingest_single_post_handles_missing_modified, test_ingest_single_post_returns_none_for_unparseable_date (+4) |
| `tests/unit/test_fetcher_handlers.py` | _article, _row, _ctx, test_handle_http_failure_writes_marker_and_logs, test_handle_off_domain_logs_error_and_clears_raw_path (+3) |
| `tests/unit/test_convergence.py` | _cp, test_no_changepoints_returns_empty, test_single_changepoint_single_feature_emits_window, test_multi_feature_alignment_within_window_detected, test_changepoints_outside_window_no_convergence (+2) |

## Entry Points

Start here when exploring this area:

- **`test_convergence_window`** (Function) — `tests/test_analysis.py:154`
- **`test_from_settings_pulls_permutation_knobs_from_analysis`** (Function) — `tests/unit/test_convergence_input.py:23`
- **`test_from_settings_passes_through_optional_signals`** (Function) — `tests/unit/test_convergence_input.py:43`
- **`test_build_applies_explicit_overrides_when_no_settings`** (Function) — `tests/unit/test_convergence_input.py:59`
- **`test_no_changepoints_returns_empty`** (Function) — `tests/unit/test_convergence.py:40`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ChangePoint` | Class | `src/forensics/models/analysis.py` | 11 |
| `DriftScores` | Class | `src/forensics/models/analysis.py` | 31 |
| `DriftSummary` | Class | `src/forensics/analysis/drift.py` | 53 |
| `ProbabilityConfig` | Class | `src/forensics/config/settings.py` | 215 |
| `HypothesisTest` | Class | `src/forensics/models/analysis.py` | 50 |
| `TracingLock` | Class | `tests/unit/test_fetcher_mutations.py` | 279 |
| `ArticleHtmlFetchContext` | Class | `src/forensics/scraper/fetcher.py` | 392 |
| `MonthlyLabeledVelocity` | Class | `src/forensics/analysis/utils.py` | 27 |
| `test_convergence_window` | Function | `tests/test_analysis.py` | 154 |
| `test_from_settings_pulls_permutation_knobs_from_analysis` | Function | `tests/unit/test_convergence_input.py` | 23 |
| `test_from_settings_passes_through_optional_signals` | Function | `tests/unit/test_convergence_input.py` | 43 |
| `test_build_applies_explicit_overrides_when_no_settings` | Function | `tests/unit/test_convergence_input.py` | 59 |
| `test_no_changepoints_returns_empty` | Function | `tests/unit/test_convergence.py` | 40 |
| `test_single_changepoint_single_feature_emits_window` | Function | `tests/unit/test_convergence.py` | 53 |
| `test_multi_feature_alignment_within_window_detected` | Function | `tests/unit/test_convergence.py` | 76 |
| `test_changepoints_outside_window_no_convergence` | Function | `tests/unit/test_convergence.py` | 100 |
| `test_empty_feature_total_returns_empty` | Function | `tests/unit/test_convergence.py` | 125 |
| `test_fully_empty_inputs_graceful` | Function | `tests/unit/test_convergence.py` | 142 |
| `build` | Function | `src/forensics/analysis/convergence.py` | 226 |
| `from_settings` | Function | `src/forensics/analysis/convergence.py` | 265 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Export_data → _project_root` | cross_community | 7 |
| `Get_rolling_feature_comparison → _project_root` | cross_community | 6 |
| `Lock_preregistration_cmd → Encode` | cross_community | 5 |
| `Get_monthly_feature_stats → _project_root` | cross_community | 5 |
| `Extract_content_features → Encode` | cross_community | 5 |
| `Get_ai_marker_spike_detection → _project_root` | cross_community | 5 |
| `_run_per_author_analysis → Cohens_d` | cross_community | 5 |
| `_run_per_author_analysis → ChangePoint` | cross_community | 5 |
| `Compute_convergence_scores → Month_key_to_range` | cross_community | 5 |
| `Compute_convergence_scores → Intervals_overlap` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 39 calls |
| Cli | 4 calls |
| Scraper | 4 calls |
| Analysis | 3 calls |
| Storage | 2 calls |
| Features | 1 calls |
| Forensics | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_convergence_window"})` — see callers and callees
2. `gitnexus_query({query: "unit"})` — find related execution flows
3. Read key files listed above for implementation details
