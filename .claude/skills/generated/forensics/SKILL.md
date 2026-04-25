---
name: forensics
description: "Skill for the Forensics area of mediaite-ghostink. 21 symbols across 12 files."
---

# Forensics

21 symbols | 12 files | Cohesion: 46%

## When to Use

- Working with code in `src/`
- Understanding how changepoints_json, convergence_json, hypothesis_tests_json work
- Modifying forensics-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/paths.py` | changepoints_json, convergence_json, hypothesis_tests_json, drift_json, centroids_npz (+3) |
| `src/forensics/analysis/drift.py` | write_drift_artifacts, _iter_ai_baseline_embedding_paths |
| `src/forensics/pipeline.py` | _pipeline_phase, _run |
| `src/forensics/analysis/orchestrator.py` | _write_per_author_json_artifacts |
| `src/forensics/analysis/comparison.py` | _editorial_target_changepoints_disk_or_compute |
| `src/forensics/analysis/changepoint.py` | run_changepoint_analysis |
| `src/forensics/cli/analyze.py` | _run_changepoint_stage |
| `tests/test_analysis_drift_pipeline.py` | test_compute_author_drift_pipeline_writes_artifacts |
| `src/forensics/storage/parquet.py` | save_numpy_compressed_atomic |
| `tests/test_analysis_infrastructure.py` | test_analysis_artifact_paths_layout |

## Entry Points

Start here when exploring this area:

- **`changepoints_json`** (Function) — `src/forensics/paths.py:43`
- **`convergence_json`** (Function) — `src/forensics/paths.py:46`
- **`hypothesis_tests_json`** (Function) — `src/forensics/paths.py:52`
- **`run_changepoint_analysis`** (Function) — `src/forensics/analysis/changepoint.py:302`
- **`test_compute_author_drift_pipeline_writes_artifacts`** (Function) — `tests/test_analysis_drift_pipeline.py:46`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ReportArgs` | Class | `src/forensics/models/report_args.py` | 7 |
| `changepoints_json` | Function | `src/forensics/paths.py` | 43 |
| `convergence_json` | Function | `src/forensics/paths.py` | 46 |
| `hypothesis_tests_json` | Function | `src/forensics/paths.py` | 52 |
| `run_changepoint_analysis` | Function | `src/forensics/analysis/changepoint.py` | 302 |
| `test_compute_author_drift_pipeline_writes_artifacts` | Function | `tests/test_analysis_drift_pipeline.py` | 46 |
| `drift_json` | Function | `src/forensics/paths.py` | 55 |
| `centroids_npz` | Function | `src/forensics/paths.py` | 61 |
| `umap_json` | Function | `src/forensics/paths.py` | 64 |
| `save_numpy_compressed_atomic` | Function | `src/forensics/storage/parquet.py` | 139 |
| `write_drift_artifacts` | Function | `src/forensics/analysis/drift.py` | 500 |
| `test_analysis_artifact_paths_layout` | Function | `tests/test_analysis_infrastructure.py` | 29 |
| `ai_baseline_dir` | Function | `src/forensics/paths.py` | 76 |
| `ai_baseline_embeddings_dir` | Function | `src/forensics/paths.py` | 80 |
| `live_ui_mode` | Function | `src/forensics/progress/rich_observer.py` | 109 |
| `_write_per_author_json_artifacts` | Function | `src/forensics/analysis/orchestrator.py` | 65 |
| `_editorial_target_changepoints_disk_or_compute` | Function | `src/forensics/analysis/comparison.py` | 272 |
| `_run_changepoint_stage` | Function | `src/forensics/cli/analyze.py` | 102 |
| `_iter_ai_baseline_embedding_paths` | Function | `src/forensics/analysis/drift.py` | 389 |
| `_pipeline_phase` | Function | `src/forensics/pipeline.py` | 43 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_run → Config_fingerprint` | cross_community | 7 |
| `Run_changepoint_analysis → Author` | cross_community | 5 |
| `Run_changepoint_analysis → _require_conn` | cross_community | 4 |
| `Run_full_analysis → Ensure_parent` | cross_community | 4 |
| `Run_full_analysis → _to_jsonable` | cross_community | 4 |
| `_run → ForensicsSettings` | cross_community | 4 |
| `_run → From_layout` | cross_community | 4 |
| `_run → Ensure_dir` | cross_community | 4 |
| `Load_ai_baseline_embeddings → Ai_baseline_dir` | cross_community | 4 |
| `Run_changepoint_analysis → From_layout` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 8 calls |
| Analysis | 7 calls |
| Unit | 6 calls |
| Scripts | 2 calls |
| Integration | 1 calls |
| Cli | 1 calls |
| Reporting | 1 calls |
| Scraper | 1 calls |

## How to Explore

1. `gitnexus_context({name: "changepoints_json"})` — see callers and callees
2. `gitnexus_query({query: "forensics"})` — find related execution flows
3. Read key files listed above for implementation details
