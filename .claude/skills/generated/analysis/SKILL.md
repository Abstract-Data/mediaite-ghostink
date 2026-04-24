---
name: analysis
description: "Skill for the Analysis area of mediaite-ghostink. 66 symbols across 13 files."
---

# Analysis

66 symbols | 13 files | Cohesion: 66%

## When to Use

- Working with code in `src/`
- Understanding how test_centroid_velocity_stationary, test_centroid_velocity_drift, test_umap_output_shape work
- Modifying analysis-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_analysis.py` | test_centroid_velocity_stationary, test_centroid_velocity_drift, test_umap_output_shape, test_drift_scores_assembly, test_drift_scores_ai_baseline_none_when_no_convergence (+7) |
| `src/forensics/analysis/drift.py` | DriftPipelineResult, track_centroid_velocity, generate_umap_projection, compute_drift_scores, load_ai_baseline_embeddings (+5) |
| `src/forensics/analysis/convergence.py` | _months_touching_window, _monthly_values_in_window, _two_halves_drop_score, compute_probability_pipeline_score, _stylometry_weights_in_window (+5) |
| `src/forensics/analysis/changepoint.py` | detect_pelt, _pelt_confidence_from_effect, _breakpoint_timestamp, _changepoints_from_breaks, changepoints_from_pelt (+2) |
| `src/forensics/analysis/orchestrator.py` | _run_per_author_analysis, _resolve_targets_and_controls, _merge_run_metadata, run_full_analysis, run_compare_only (+1) |
| `src/forensics/paths.py` | combined_umap_json, comparison_report_json, run_metadata_json, closed_interval_contains |
| `src/forensics/analysis/timeseries.py` | compute_rolling_stats, stl_decompose, _padded_column, _compute_feature_timeseries |
| `src/forensics/analysis/comparison.py` | _numeric_feature_columns, _load_control_frames_and_pooled, _two_sample_feature_comparisons, compare_target_to_controls |
| `tests/unit/test_monthkeys.py` | test_iter_months_in_window_trivial, test_iter_months_in_window_preserves_input_order, test_iter_months_in_window_empty_when_no_overlap |
| `src/forensics/cli/analyze.py` | _run_drift_stage, _run_full_analysis_stage |

## Entry Points

Start here when exploring this area:

- **`test_centroid_velocity_stationary`** (Function) — `tests/test_analysis.py:283`
- **`test_centroid_velocity_drift`** (Function) — `tests/test_analysis.py:293`
- **`test_umap_output_shape`** (Function) — `tests/test_analysis.py:374`
- **`test_drift_scores_assembly`** (Function) — `tests/test_analysis.py:386`
- **`test_drift_scores_ai_baseline_none_when_no_convergence`** (Function) — `tests/test_analysis.py:406`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `DriftPipelineResult` | Class | `src/forensics/analysis/drift.py` | 37 |
| `test_centroid_velocity_stationary` | Function | `tests/test_analysis.py` | 283 |
| `test_centroid_velocity_drift` | Function | `tests/test_analysis.py` | 293 |
| `test_umap_output_shape` | Function | `tests/test_analysis.py` | 374 |
| `test_drift_scores_assembly` | Function | `tests/test_analysis.py` | 386 |
| `test_drift_scores_ai_baseline_none_when_no_convergence` | Function | `tests/test_analysis.py` | 406 |
| `combined_umap_json` | Function | `src/forensics/paths.py` | 73 |
| `track_centroid_velocity` | Function | `src/forensics/analysis/drift.py` | 175 |
| `generate_umap_projection` | Function | `src/forensics/analysis/drift.py` | 279 |
| `compute_drift_scores` | Function | `src/forensics/analysis/drift.py` | 333 |
| `load_ai_baseline_embeddings` | Function | `src/forensics/analysis/drift.py` | 387 |
| `compute_author_drift_pipeline` | Function | `src/forensics/analysis/drift.py` | 490 |
| `run_drift_analysis` | Function | `src/forensics/analysis/drift.py` | 551 |
| `test_pelt_synthetic_mean_shift` | Function | `tests/test_analysis.py` | 38 |
| `test_pelt_no_change` | Function | `tests/test_analysis.py` | 48 |
| `test_analyze_author_feature_changepoints_runs` | Function | `tests/test_analysis.py` | 228 |
| `timestamps_from_frame` | Function | `src/forensics/utils/datetime.py` | 33 |
| `detect_pelt` | Function | `src/forensics/analysis/changepoint.py` | 54 |
| `changepoints_from_pelt` | Function | `src/forensics/analysis/changepoint.py` | 217 |
| `changepoints_from_bocpd` | Function | `src/forensics/analysis/changepoint.py` | 236 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_compare_only → Author` | cross_community | 6 |
| `Run_compare_only → _read_parquet_schema_version` | cross_community | 6 |
| `Run_compare_only → SchemaMigrationRequired` | cross_community | 6 |
| `Run_compare_only → Scan_features` | cross_community | 6 |
| `Run_drift_analysis → Author` | cross_community | 5 |
| `Run_full_analysis → Author` | cross_community | 5 |
| `Run_full_analysis → ForensicsSettings` | cross_community | 5 |
| `Compare_target_to_controls → _read_parquet_schema_version` | cross_community | 5 |
| `Compare_target_to_controls → SchemaMigrationRequired` | cross_community | 5 |
| `Compare_target_to_controls → Scan_features` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 22 calls |
| Unit | 14 calls |
| Forensics | 8 calls |
| Storage | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_centroid_velocity_stationary"})` — see callers and callees
2. `gitnexus_query({query: "analysis"})` — find related execution flows
3. Read key files listed above for implementation details
