---
name: progress
description: "Skill for the Progress area of mediaite-ghostink. 20 symbols across 3 files."
---

# Progress

20 symbols | 3 files | Cohesion: 90%

## When to Use

- Working with code in `src/`
- Understanding how pipeline_stage_start, pipeline_stage_end, metadata_author_started work
- Modifying progress-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/progress/rich_observer.py` | _describe, pipeline_stage_start, pipeline_stage_end, metadata_author_started, metadata_author_done (+9) |
| `src/forensics/progress/observer.py` | metadata_author_started, metadata_author_done, pipeline_run_phase_start, pipeline_run_phase_end |
| `tests/test_pipeline_progress.py` | test_managed_rich_observer_false_yields_none, _runner |

## Entry Points

Start here when exploring this area:

- **`pipeline_stage_start`** (Function) — `src/forensics/progress/rich_observer.py:65`
- **`pipeline_stage_end`** (Function) — `src/forensics/progress/rich_observer.py:68`
- **`metadata_author_started`** (Function) — `src/forensics/progress/rich_observer.py:71`
- **`metadata_author_done`** (Function) — `src/forensics/progress/rich_observer.py:74`
- **`fetch_progress`** (Function) — `src/forensics/progress/rich_observer.py:77`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `RichPipelineObserver` | Class | `src/forensics/progress/rich_observer.py` | 20 |
| `pipeline_stage_start` | Function | `src/forensics/progress/rich_observer.py` | 65 |
| `pipeline_stage_end` | Function | `src/forensics/progress/rich_observer.py` | 68 |
| `metadata_author_started` | Function | `src/forensics/progress/rich_observer.py` | 71 |
| `metadata_author_done` | Function | `src/forensics/progress/rich_observer.py` | 74 |
| `fetch_progress` | Function | `src/forensics/progress/rich_observer.py` | 77 |
| `pipeline_run_phase_start` | Function | `src/forensics/progress/rich_observer.py` | 81 |
| `pipeline_run_phase_end` | Function | `src/forensics/progress/rich_observer.py` | 84 |
| `survey_author_started` | Function | `src/forensics/progress/rich_observer.py` | 87 |
| `survey_author_finished` | Function | `src/forensics/progress/rich_observer.py` | 90 |
| `test_managed_rich_observer_false_yields_none` | Function | `tests/test_pipeline_progress.py` | 94 |
| `start` | Function | `src/forensics/progress/rich_observer.py` | 46 |
| `stop` | Function | `src/forensics/progress/rich_observer.py` | 53 |
| `managed_rich_observer` | Function | `src/forensics/progress/rich_observer.py` | 96 |
| `metadata_author_started` | Function | `src/forensics/progress/observer.py` | 39 |
| `metadata_author_done` | Function | `src/forensics/progress/observer.py` | 42 |
| `pipeline_run_phase_start` | Function | `src/forensics/progress/observer.py` | 48 |
| `pipeline_run_phase_end` | Function | `src/forensics/progress/observer.py` | 51 |
| `_describe` | Function | `src/forensics/progress/rich_observer.py` | 60 |
| `_runner` | Function | `tests/test_pipeline_progress.py` | 168 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Scrape → RichPipelineObserver` | cross_community | 3 |
| `Scrape → Start` | cross_community | 3 |
| `Scrape → Stop` | cross_community | 3 |

## How to Explore

1. `gitnexus_context({name: "pipeline_stage_start"})` — see callers and callees
2. `gitnexus_query({query: "progress"})` — find related execution flows
3. Read key files listed above for implementation details
