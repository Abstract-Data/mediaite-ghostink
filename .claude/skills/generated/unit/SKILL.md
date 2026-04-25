---
name: unit
description: "Skill for the Unit area of mediaite-ghostink. 225 symbols across 45 files."
---

# Unit

225 symbols | 45 files | Cohesion: 72%

## When to Use

- Working with code in `tests/`
- Understanding how test_handle_http_failure_writes_marker_and_logs, test_handle_off_domain_logs_error_and_clears_raw_path, test_handle_success_writes_parsed_body_and_bumps_counter work
- Modifying unit-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/unit/test_statistics.py` | _make_test, test_apply_correction_empty_is_noop, test_apply_correction_bonferroni_scales_by_n, test_apply_correction_bonferroni_clips_at_one, test_apply_correction_benjamini_hochberg (+18) |
| `tests/unit/test_duckdb_validation.py` | test_validated_parquet_pattern_accepts_plain_glob, test_validated_parquet_pattern_rejects_empty, test_validated_parquet_pattern_rejects_remote_uris, test_validated_parquet_pattern_rejects_control_chars, test_validated_parquet_pattern_escapes_single_quotes (+7) |
| `tests/unit/test_fetcher_mutations.py` | _make_article, test_persist_and_log_off_domain_branch, test_persist_and_log_skips_when_row_missing, test_persist_and_log_counter_is_shared_across_branches, test_persist_and_log_dispatches_via_asyncio_to_thread (+7) |
| `tests/unit/test_content_lda.py` | test_empty_corpus_returns_nan, test_single_document_corpus_returns_nan, test_two_document_corpus_returns_nan, test_identical_documents_yield_low_entropy, test_corpus_with_no_vocabulary_returns_nan (+6) |
| `src/forensics/scraper/fetcher.py` | _resume_skip_fetch, _apply_http_failed_mutation, _apply_off_domain_mutation, _handle_http_failure, _handle_off_domain (+5) |
| `tests/unit/test_velocity.py` | test_compute_velocity_acceleration_requires_six_points, test_compute_velocity_acceleration_clamps_to_unit_interval, test_compute_velocity_acceleration_returns_zero_for_zero_early, test_compute_velocity_acceleration_mid_range, test_describe_velocity_acceleration_pct_none_when_undefined (+5) |
| `tests/unit/test_json_io.py` | _Sample, test_write_json_artifact_creates_parents, test_write_json_artifact_serialises_single_model, test_write_json_artifact_serialises_list_of_models, test_write_json_artifact_handles_datetime_default_str (+4) |
| `src/forensics/analysis/convergence.py` | _baseline_curve_as_dates, build, _VelocityStats, _precompute_velocity_stats, compute_convergence_scores (+4) |
| `tests/unit/test_crawler_ingest_single_post.py` | _wp_post, test_ingest_single_post_parses_metadata_only_row, test_ingest_single_post_parses_content_when_provided, test_ingest_single_post_handles_missing_modified, test_ingest_single_post_returns_none_for_unparseable_date (+4) |
| `tests/unit/test_fetcher_handlers.py` | _article, _row, _ctx, test_handle_http_failure_writes_marker_and_logs, test_handle_off_domain_logs_error_and_clears_raw_path (+3) |

## Entry Points

Start here when exploring this area:

- **`test_handle_http_failure_writes_marker_and_logs`** (Function) — `tests/unit/test_fetcher_handlers.py:83`
- **`test_handle_off_domain_logs_error_and_clears_raw_path`** (Function) — `tests/unit/test_fetcher_handlers.py:110`
- **`test_handle_success_writes_parsed_body_and_bumps_counter`** (Function) — `tests/unit/test_fetcher_handlers.py:149`
- **`test_handle_success_skips_when_row_filled_before_parse`** (Function) — `tests/unit/test_fetcher_handlers.py:193`
- **`test_handle_success_skips_between_parse_and_persist`** (Function) — `tests/unit/test_fetcher_handlers.py:222`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ChangePoint` | Class | `src/forensics/models/analysis.py` | 11 |
| `RateLimiter` | Class | `src/forensics/scraper/fetcher.py` | 50 |
| `ArticleHtmlFetchContext` | Class | `src/forensics/scraper/fetcher.py` | 392 |
| `ProbabilityConfig` | Class | `src/forensics/config/settings.py` | 215 |
| `HypothesisTest` | Class | `src/forensics/models/analysis.py` | 50 |
| `TracingLock` | Class | `tests/unit/test_fetcher_mutations.py` | 279 |
| `DriftScores` | Class | `src/forensics/models/analysis.py` | 31 |
| `MonthlyLabeledVelocity` | Class | `src/forensics/analysis/utils.py` | 27 |
| `test_handle_http_failure_writes_marker_and_logs` | Function | `tests/unit/test_fetcher_handlers.py` | 83 |
| `test_handle_off_domain_logs_error_and_clears_raw_path` | Function | `tests/unit/test_fetcher_handlers.py` | 110 |
| `test_handle_success_writes_parsed_body_and_bumps_counter` | Function | `tests/unit/test_fetcher_handlers.py` | 149 |
| `test_handle_success_skips_when_row_filled_before_parse` | Function | `tests/unit/test_fetcher_handlers.py` | 193 |
| `test_handle_success_skips_between_parse_and_persist` | Function | `tests/unit/test_fetcher_handlers.py` | 222 |
| `content_hash` | Function | `src/forensics/utils/hashing.py` | 9 |
| `run_metadata_json` | Function | `src/forensics/paths.py` | 70 |
| `test_write_json_artifact_creates_parents` | Function | `tests/unit/test_json_io.py` | 18 |
| `test_write_json_artifact_serialises_single_model` | Function | `tests/unit/test_json_io.py` | 25 |
| `test_write_json_artifact_serialises_list_of_models` | Function | `tests/unit/test_json_io.py` | 31 |
| `test_write_json_artifact_handles_datetime_default_str` | Function | `tests/unit/test_json_io.py` | 39 |
| `test_write_json_artifact_atomic_replace` | Function | `tests/unit/test_json_io.py` | 48 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Export_data → _project_root` | cross_community | 7 |
| `Get_rolling_feature_comparison → _project_root` | cross_community | 6 |
| `Lock_preregistration_cmd → Encode` | cross_community | 5 |
| `Get_monthly_feature_stats → _project_root` | cross_community | 5 |
| `Run_full_analysis → Author` | cross_community | 5 |
| `Run_full_analysis → ForensicsSettings` | cross_community | 5 |
| `Get_ai_marker_spike_detection → _project_root` | cross_community | 5 |
| `Extract_content_features → Encode` | cross_community | 5 |
| `_run_per_author_analysis → Cohens_d` | cross_community | 5 |
| `_run_per_author_analysis → ChangePoint` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 30 calls |
| Analysis | 11 calls |
| Scraper | 7 calls |
| Forensics | 6 calls |
| Features | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_handle_http_failure_writes_marker_and_logs"})` — see callers and callees
2. `gitnexus_query({query: "unit"})` — find related execution flows
3. Read key files listed above for implementation details
