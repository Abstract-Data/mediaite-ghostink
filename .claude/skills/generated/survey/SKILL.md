---
name: survey
description: "Skill for the Survey area of mediaite-ghostink. 45 symbols across 7 files."
---

# Survey

45 symbols | 7 files | Cohesion: 73%

## When to Use

- Working with code in `src/`
- Understanding how test_survey_dry_run_no_analysis, test_survey_orchestrator_checkpoints_after_each_author, test_survey_orchestrator_resume_skips_completed work
- Modifying survey-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/survey/orchestrator.py` | SurveyResult, _run_dir_for, _checkpoint_path, _load_checkpoint, _write_checkpoint (+13) |
| `tests/test_survey.py` | _seed_qualified_corpus, _patch_orchestrator_side_effects, test_survey_dry_run_no_analysis, test_survey_orchestrator_checkpoints_after_each_author, test_survey_orchestrator_resume_skips_completed (+6) |
| `src/forensics/survey/scoring.py` | SurveyScore, ControlValidation, identify_natural_controls, validate_against_controls, _pipeline_a_score (+6) |
| `src/forensics/tui/pipeline_app.py` | _thread_pipeline, _go |
| `src/forensics/progress/observer.py` | NoOpPipelineObserver |
| `tests/test_calibration.py` | fake_compute_composite_score |
| `tests/test_pipeline_progress.py` | test_survey_completion_exit_code |

## Entry Points

Start here when exploring this area:

- **`test_survey_dry_run_no_analysis`** (Function) — `tests/test_survey.py:450`
- **`test_survey_orchestrator_checkpoints_after_each_author`** (Function) — `tests/test_survey.py:484`
- **`test_survey_orchestrator_resume_skips_completed`** (Function) — `tests/test_survey.py:514`
- **`test_survey_forwards_post_year_bounds_to_dispatch_scrape`** (Function) — `tests/test_survey.py:562`
- **`test_survey_observer_hooks_fire_per_author`** (Function) — `tests/test_survey.py:616`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `SurveyResult` | Class | `src/forensics/survey/orchestrator.py` | 46 |
| `NoOpPipelineObserver` | Class | `src/forensics/progress/observer.py` | 61 |
| `SurveyScore` | Class | `src/forensics/survey/scoring.py` | 28 |
| `ControlValidation` | Class | `src/forensics/survey/scoring.py` | 44 |
| `SurveyReport` | Class | `src/forensics/survey/orchestrator.py` | 58 |
| `test_survey_dry_run_no_analysis` | Function | `tests/test_survey.py` | 450 |
| `test_survey_orchestrator_checkpoints_after_each_author` | Function | `tests/test_survey.py` | 484 |
| `test_survey_orchestrator_resume_skips_completed` | Function | `tests/test_survey.py` | 514 |
| `test_survey_forwards_post_year_bounds_to_dispatch_scrape` | Function | `tests/test_survey.py` | 562 |
| `test_survey_observer_hooks_fire_per_author` | Function | `tests/test_survey.py` | 616 |
| `test_survey_report_is_instance_of_SurveyReport` | Function | `tests/test_survey.py` | 654 |
| `run_survey` | Function | `src/forensics/survey/orchestrator.py` | 426 |
| `test_natural_controls_identified_from_mixed_results` | Function | `tests/test_survey.py` | 335 |
| `fake_compute_composite_score` | Function | `tests/test_calibration.py` | 286 |
| `identify_natural_controls` | Function | `src/forensics/survey/scoring.py` | 219 |
| `validate_against_controls` | Function | `src/forensics/survey/scoring.py` | 239 |
| `test_signal_strength_classification_thresholds` | Function | `tests/test_survey.py` | 326 |
| `classify_signal` | Function | `src/forensics/survey/scoring.py` | 94 |
| `compute_composite_score` | Function | `src/forensics/survey/scoring.py` | 153 |
| `test_survey_completion_exit_code` | Function | `tests/test_pipeline_progress.py` | 123 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_thread_pipeline → Config_fingerprint` | cross_community | 7 |
| `_thread_pipeline → _collect_hash_enumerated_fields` | cross_community | 6 |
| `_thread_pipeline → ForensicsSettings` | cross_community | 6 |
| `_thread_pipeline → PreflightCheck` | cross_community | 5 |
| `_thread_pipeline → _run_dir_for` | cross_community | 4 |
| `_thread_pipeline → SurveyReport` | cross_community | 4 |
| `Generate_evidence_narrative → _pipeline_a_score` | cross_community | 3 |
| `Generate_evidence_narrative → _pipeline_b_score` | cross_community | 3 |
| `Generate_evidence_narrative → _pipeline_c_score` | cross_community | 3 |
| `Generate_evidence_narrative → _convergence_score` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 17 calls |
| Unit | 2 calls |
| Forensics | 2 calls |
| Analysis | 1 calls |
| Integration | 1 calls |
| Cli | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_survey_dry_run_no_analysis"})` — see callers and callees
2. `gitnexus_query({query: "survey"})` — find related execution flows
3. Read key files listed above for implementation details
