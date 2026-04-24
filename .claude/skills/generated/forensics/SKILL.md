---
name: forensics
description: "Skill for the Forensics area of mediaite-ghostink. 44 symbols across 13 files."
---

# Forensics

44 symbols | 13 files | Cohesion: 65%

## When to Use

- Working with code in `src/`
- Understanding how test_run_author_batches_skips_rich_when_disabled, test_analysis_artifact_paths_layout, features_parquet work
- Modifying forensics-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/preflight.py` | PreflightCheck, check_python_version, check_spacy_model, check_sentence_transformer, check_quarto (+5) |
| `src/forensics/paths.py` | features_parquet, changepoints_json, convergence_json, result_json, hypothesis_tests_json (+4) |
| `tests/test_preflight.py` | _stub_passing_checks, test_preflight_all_pass, test_preflight_missing_spacy, test_preflight_disk_space_low, test_preflight_config_parse_error (+3) |
| `src/forensics/analysis/comparison.py` | _load_or_compute_changepoints, _load_target_author_and_frame, _editorial_signal_for_target, _editorial_target_changepoints_disk_or_compute |
| `src/forensics/cli/analyze.py` | build, _run_changepoint_stage, _run_timeseries_stage |
| `src/forensics/analysis/timeseries.py` | detect_bursts, run_timeseries_analysis |
| `src/forensics/pipeline.py` | _pipeline_phase, _run |
| `tests/test_pipeline_progress.py` | test_run_author_batches_skips_rich_when_disabled |
| `tests/test_analysis_infrastructure.py` | test_analysis_artifact_paths_layout |
| `src/forensics/analysis/orchestrator.py` | _write_per_author_json_artifacts |

## Entry Points

Start here when exploring this area:

- **`test_run_author_batches_skips_rich_when_disabled`** (Function) — `tests/test_pipeline_progress.py:132`
- **`test_analysis_artifact_paths_layout`** (Function) — `tests/test_analysis_infrastructure.py:29`
- **`features_parquet`** (Function) — `src/forensics/paths.py:40`
- **`changepoints_json`** (Function) — `src/forensics/paths.py:43`
- **`convergence_json`** (Function) — `src/forensics/paths.py:46`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PreflightCheck` | Class | `src/forensics/preflight.py` | 37 |
| `ReportArgs` | Class | `src/forensics/models/report_args.py` | 7 |
| `test_run_author_batches_skips_rich_when_disabled` | Function | `tests/test_pipeline_progress.py` | 132 |
| `test_analysis_artifact_paths_layout` | Function | `tests/test_analysis_infrastructure.py` | 29 |
| `features_parquet` | Function | `src/forensics/paths.py` | 40 |
| `changepoints_json` | Function | `src/forensics/paths.py` | 43 |
| `convergence_json` | Function | `src/forensics/paths.py` | 46 |
| `result_json` | Function | `src/forensics/paths.py` | 49 |
| `hypothesis_tests_json` | Function | `src/forensics/paths.py` | 52 |
| `ai_baseline_embeddings_dir` | Function | `src/forensics/paths.py` | 76 |
| `from_project` | Function | `src/forensics/paths.py` | 81 |
| `load_feature_frame_for_author` | Function | `src/forensics/paths.py` | 129 |
| `resolve_author_rows` | Function | `src/forensics/paths.py` | 156 |
| `build` | Function | `src/forensics/cli/analyze.py` | 36 |
| `detect_bursts` | Function | `src/forensics/analysis/timeseries.py` | 150 |
| `run_timeseries_analysis` | Function | `src/forensics/analysis/timeseries.py` | 218 |
| `run_changepoint_analysis` | Function | `src/forensics/analysis/changepoint.py` | 302 |
| `test_preflight_all_pass` | Function | `tests/test_preflight.py` | 68 |
| `test_preflight_missing_spacy` | Function | `tests/test_preflight.py` | 81 |
| `test_preflight_disk_space_low` | Function | `tests/test_preflight.py` | 117 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_all → Config_fingerprint` | cross_community | 7 |
| `On_button_pressed → Config_fingerprint` | cross_community | 7 |
| `On_mount → Config_fingerprint` | cross_community | 7 |
| `_run → Config_fingerprint` | cross_community | 7 |
| `Preflight → Config_fingerprint` | cross_community | 6 |
| `Run_all → ForensicsSettings` | cross_community | 6 |
| `On_button_pressed → ForensicsSettings` | cross_community | 6 |
| `Validate_config → Config_fingerprint` | cross_community | 6 |
| `Run_compare_only → Author` | cross_community | 6 |
| `Run_compare_only → _read_parquet_schema_version` | cross_community | 6 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 14 calls |
| Unit | 8 calls |
| Analysis | 6 calls |
| Features | 2 calls |
| Integration | 1 calls |
| Cli | 1 calls |
| Reporting | 1 calls |
| Storage | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_run_author_batches_skips_rich_when_disabled"})` — see callers and callees
2. `gitnexus_query({query: "forensics"})` — find related execution flows
3. Read key files listed above for implementation details
