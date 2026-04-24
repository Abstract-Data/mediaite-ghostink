---
name: calibration
description: "Skill for the Calibration area of mediaite-ghostink. 19 symbols across 4 files."
---

# Calibration

19 symbols | 4 files | Cohesion: 62%

## When to Use

- Working with code in `src/`
- Understanding how test_calibration_dry_run_skips_everything, run_calibration, calibrate work
- Modifying calibration-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/calibration/runner.py` | CalibrationTrial, _TrialOutcome, _earliest_changepoint_date, _outcome_from_analysis, _pick_splice_date (+8) |
| `src/forensics/calibration/synthetic.py` | SyntheticCorpus, _sorted_by_date, build_spliced_corpus, build_negative_control |
| `tests/test_calibration.py` | test_calibration_dry_run_skips_everything |
| `src/forensics/cli/calibrate.py` | calibrate |

## Entry Points

Start here when exploring this area:

- **`test_calibration_dry_run_skips_everything`** (Function) — `tests/test_calibration.py:403`
- **`run_calibration`** (Function) — `src/forensics/calibration/runner.py:372`
- **`calibrate`** (Function) — `src/forensics/cli/calibrate.py:22`
- **`build_spliced_corpus`** (Function) — `src/forensics/calibration/synthetic.py:46`
- **`build_negative_control`** (Function) — `src/forensics/calibration/synthetic.py:120`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `CalibrationTrial` | Class | `src/forensics/calibration/runner.py` | 59 |
| `CalibrationReport` | Class | `src/forensics/calibration/runner.py` | 73 |
| `SyntheticCorpus` | Class | `src/forensics/calibration/synthetic.py` | 27 |
| `test_calibration_dry_run_skips_everything` | Function | `tests/test_calibration.py` | 403 |
| `run_calibration` | Function | `src/forensics/calibration/runner.py` | 372 |
| `calibrate` | Function | `src/forensics/cli/calibrate.py` | 22 |
| `build_spliced_corpus` | Function | `src/forensics/calibration/synthetic.py` | 46 |
| `build_negative_control` | Function | `src/forensics/calibration/synthetic.py` | 120 |
| `_TrialOutcome` | Class | `src/forensics/calibration/runner.py` | 86 |
| `_RunContext` | Class | `src/forensics/calibration/runner.py` | 274 |
| `_earliest_changepoint_date` | Function | `src/forensics/calibration/runner.py` | 137 |
| `_outcome_from_analysis` | Function | `src/forensics/calibration/runner.py` | 144 |
| `_pick_splice_date` | Function | `src/forensics/calibration/runner.py` | 223 |
| `_execute_trial` | Function | `src/forensics/calibration/runner.py` | 285 |
| `_run_positive_trials` | Function | `src/forensics/calibration/runner.py` | 307 |
| `_run_negative_trials` | Function | `src/forensics/calibration/runner.py` | 347 |
| `_load_ai_articles` | Function | `src/forensics/calibration/runner.py` | 186 |
| `_write_calibration_report` | Function | `src/forensics/calibration/runner.py` | 466 |
| `_sorted_by_date` | Function | `src/forensics/calibration/synthetic.py` | 42 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Calibrate → Parse_datetime` | cross_community | 7 |
| `Calibrate → Article` | cross_community | 7 |
| `Calibrate → Config_fingerprint` | cross_community | 6 |
| `Calibrate → Author` | cross_community | 6 |
| `Calibrate → _validate_batch_size` | cross_community | 6 |
| `Calibrate → _require_conn` | cross_community | 6 |
| `Calibrate → Repository` | cross_community | 4 |
| `Calibrate → ForensicsSettings` | cross_community | 3 |
| `Calibrate → CalibrationReport` | intra_community | 3 |
| `Calibrate → _load_ai_articles` | intra_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 6 calls |
| Survey | 1 calls |
| Unit | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_calibration_dry_run_skips_everything"})` — see callers and callees
2. `gitnexus_query({query: "calibration"})` — find related execution flows
3. Read key files listed above for implementation details
