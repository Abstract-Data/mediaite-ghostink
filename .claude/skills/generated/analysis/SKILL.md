---
name: analysis
description: "Skill for the Analysis area of mediaite-ghostink. 70 symbols across 13 files."
---

# Analysis

70 symbols | 13 files | Cohesion: 57%

## When to Use

- Working with code in `src/`
- Understanding how test_pelt_synthetic_mean_shift, test_pelt_no_change, test_analyze_author_feature_changepoints_runs work
- Modifying analysis-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_analysis.py` | _minimal_settings, test_pelt_synthetic_mean_shift, test_pelt_no_change, test_analyze_author_feature_changepoints_runs, test_umap_output_shape (+7) |
| `src/forensics/analysis/drift.py` | DriftPipelineResult, generate_umap_projection, compute_drift_scores, compute_author_drift_pipeline, run_drift_analysis (+7) |
| `src/forensics/analysis/convergence.py` | _monthly_values_in_window, _two_halves_drop_score, compute_probability_pipeline_score, _pipeline_a_from_stylometry, _ai_curve_signal (+4) |
| `src/forensics/analysis/comparison.py` | _load_target_author_and_frame, _load_control_frames_and_pooled, _numeric_feature_columns, _finite_values, _feature_coverage_diagnostics (+3) |
| `src/forensics/analysis/changepoint.py` | detect_pelt, _pelt_confidence_from_effect, _breakpoint_timestamp, _changepoints_from_breaks, changepoints_from_pelt (+2) |
| `src/forensics/analysis/orchestrator.py` | _run_per_author_analysis, _resolve_targets_and_controls, run_compare_only, _validate_compare_artifact_hashes, _run_target_control_comparisons |
| `src/forensics/paths.py` | combined_umap_json, features_parquet, load_feature_frame_for_author, comparison_report_json, closed_interval_contains |
| `src/forensics/analysis/timeseries.py` | compute_rolling_stats, stl_decompose, _padded_column, _compute_feature_timeseries, run_timeseries_analysis |
| `src/forensics/cli/analyze.py` | _run_drift_stage, _run_timeseries_stage |
| `src/forensics/utils/provenance.py` | compute_analysis_config_hash, validate_analysis_result_config_hashes |

## Entry Points

Start here when exploring this area:

- **`test_pelt_synthetic_mean_shift`** (Function) — `tests/test_analysis.py:38`
- **`test_pelt_no_change`** (Function) — `tests/test_analysis.py:48`
- **`test_analyze_author_feature_changepoints_runs`** (Function) — `tests/test_analysis.py:228`
- **`timestamps_from_frame`** (Function) — `src/forensics/utils/datetime.py:33`
- **`detect_pelt`** (Function) — `src/forensics/analysis/changepoint.py:54`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `DriftPipelineResult` | Class | `src/forensics/analysis/drift.py` | 39 |
| `DriftSummary` | Class | `src/forensics/analysis/drift.py` | 55 |
| `test_pelt_synthetic_mean_shift` | Function | `tests/test_analysis.py` | 38 |
| `test_pelt_no_change` | Function | `tests/test_analysis.py` | 48 |
| `test_analyze_author_feature_changepoints_runs` | Function | `tests/test_analysis.py` | 228 |
| `timestamps_from_frame` | Function | `src/forensics/utils/datetime.py` | 33 |
| `detect_pelt` | Function | `src/forensics/analysis/changepoint.py` | 54 |
| `changepoints_from_pelt` | Function | `src/forensics/analysis/changepoint.py` | 217 |
| `changepoints_from_bocpd` | Function | `src/forensics/analysis/changepoint.py` | 236 |
| `analyze_author_feature_changepoints` | Function | `src/forensics/analysis/changepoint.py` | 257 |
| `test_umap_output_shape` | Function | `tests/test_analysis.py` | 374 |
| `test_drift_scores_assembly` | Function | `tests/test_analysis.py` | 386 |
| `test_drift_scores_ai_baseline_none_when_no_convergence` | Function | `tests/test_analysis.py` | 406 |
| `combined_umap_json` | Function | `src/forensics/paths.py` | 73 |
| `generate_umap_projection` | Function | `src/forensics/analysis/drift.py` | 281 |
| `compute_drift_scores` | Function | `src/forensics/analysis/drift.py` | 335 |
| `compute_author_drift_pipeline` | Function | `src/forensics/analysis/drift.py` | 526 |
| `run_drift_analysis` | Function | `src/forensics/analysis/drift.py` | 587 |
| `test_centroid_velocity_stationary` | Function | `tests/test_analysis.py` | 283 |
| `test_centroid_velocity_drift` | Function | `tests/test_analysis.py` | 293 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Report → _collect_hash_enumerated_fields` | cross_community | 8 |
| `Run_compare_only → _collect_hash_enumerated_fields` | cross_community | 6 |
| `Run_compare_only → Author` | cross_community | 6 |
| `Run_compare_only → _read_parquet_schema_version` | cross_community | 6 |
| `Run_compare_only → SchemaMigrationRequired` | cross_community | 6 |
| `Run_timeseries_analysis → Author` | cross_community | 5 |
| `Run_drift_analysis → Author` | cross_community | 5 |
| `Run_full_analysis → Author` | cross_community | 5 |
| `Run_full_analysis → ForensicsSettings` | cross_community | 5 |
| `Compare_target_to_controls → Scan_features` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 34 calls |
| Unit | 15 calls |
| Forensics | 4 calls |
| Storage | 2 calls |
| Scripts | 1 calls |
| Scraper | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_pelt_synthetic_mean_shift"})` — see callers and callees
2. `gitnexus_query({query: "analysis"})` — find related execution flows
3. Read key files listed above for implementation details
