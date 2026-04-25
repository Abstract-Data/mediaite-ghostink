---
name: scripts
description: "Skill for the Scripts area of mediaite-ghostink. 31 symbols across 8 files."
---

# Scripts

31 symbols | 8 files | Cohesion: 47%

## When to Use

- Working with code in `scripts/`
- Understanding how test_run_author_batches_skips_rich_when_disabled, from_project, build work
- Modifying scripts-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `scripts/generate_phase8_notebooks.py` | _lines, code, nb02, nb06, md (+11) |
| `scripts/bench_phase15.py` | PerAuthorStageTimings, PerAuthorBench, _get_git_sha, _bench_one_author, _main |
| `scripts/generate_baseline.py` | _parser, _amain, main |
| `tests/test_baseline.py` | _patch_mock_transport, test_preflight_with_all_models, test_preflight_reports_missing_model |
| `tests/test_pipeline_progress.py` | test_run_author_batches_skips_rich_when_disabled |
| `src/forensics/paths.py` | from_project |
| `src/forensics/cli/analyze.py` | build |
| `src/forensics/baseline/preflight.py` | preflight_check |

## Entry Points

Start here when exploring this area:

- **`test_run_author_batches_skips_rich_when_disabled`** (Function) — `tests/test_pipeline_progress.py:132`
- **`from_project`** (Function) — `src/forensics/paths.py:85`
- **`build`** (Function) — `src/forensics/cli/analyze.py:36`
- **`main`** (Function) — `scripts/generate_baseline.py:91`
- **`test_preflight_with_all_models`** (Function) — `tests/test_baseline.py:165`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PerAuthorStageTimings` | Class | `scripts/bench_phase15.py` | 36 |
| `PerAuthorBench` | Class | `scripts/bench_phase15.py` | 49 |
| `test_run_author_batches_skips_rich_when_disabled` | Function | `tests/test_pipeline_progress.py` | 132 |
| `from_project` | Function | `src/forensics/paths.py` | 85 |
| `build` | Function | `src/forensics/cli/analyze.py` | 36 |
| `main` | Function | `scripts/generate_baseline.py` | 91 |
| `test_preflight_with_all_models` | Function | `tests/test_baseline.py` | 165 |
| `test_preflight_reports_missing_model` | Function | `tests/test_baseline.py` | 176 |
| `preflight_check` | Function | `src/forensics/baseline/preflight.py` | 11 |
| `code` | Function | `scripts/generate_phase8_notebooks.py` | 33 |
| `nb02` | Function | `scripts/generate_phase8_notebooks.py` | 239 |
| `nb06` | Function | `scripts/generate_phase8_notebooks.py` | 407 |
| `md` | Function | `scripts/generate_phase8_notebooks.py` | 29 |
| `nb04` | Function | `scripts/generate_phase8_notebooks.py` | 321 |
| `nb08` | Function | `scripts/generate_phase8_notebooks.py` | 489 |
| `nb09` | Function | `scripts/generate_phase8_notebooks.py` | 522 |
| `write_nb` | Function | `scripts/generate_phase8_notebooks.py` | 75 |
| `nb01` | Function | `scripts/generate_phase8_notebooks.py` | 171 |
| `nb05` | Function | `scripts/generate_phase8_notebooks.py` | 363 |
| `nb00` | Function | `scripts/generate_phase8_notebooks.py` | 82 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Config_fingerprint` | cross_community | 7 |
| `Main → Author` | cross_community | 7 |
| `Main → _validate_batch_size` | cross_community | 7 |
| `Main → ForensicsSettings` | cross_community | 6 |
| `Main → _require_conn` | cross_community | 6 |
| `Main → Repository` | cross_community | 5 |
| `Analyze → From_layout` | cross_community | 5 |
| `_main → Config_fingerprint` | cross_community | 5 |
| `Main → _lines` | cross_community | 4 |
| `Main → _nb` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 6 calls |
| Baseline | 1 calls |
| Unit | 1 calls |
| Progress | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_run_author_batches_skips_rich_when_disabled"})` — see callers and callees
2. `gitnexus_query({query: "scripts"})` — find related execution flows
3. Read key files listed above for implementation details
