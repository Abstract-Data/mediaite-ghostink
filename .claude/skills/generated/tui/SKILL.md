---
name: tui
description: "Skill for the Tui area of mediaite-ghostink. 29 symbols across 5 files."
---

# Tui

29 symbols | 5 files | Cohesion: 89%

## When to Use

- Working with code in `src/`
- Understanding how pipeline_stage_start, pipeline_stage_end, fetch_progress work
- Modifying tui-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/tui/pipeline_app.py` | _dispatch, pipeline_stage_start, pipeline_stage_end, fetch_progress, pipeline_run_phase_start (+20) |
| `tests/test_tui.py` | test_tui_app_mounts |
| `src/forensics/tui/app.py` | ForensicsSetupApp |
| `src/forensics/tui/__init__.py` | main |
| `src/forensics/cli/__init__.py` | setup_wizard |

## Entry Points

Start here when exploring this area:

- **`pipeline_stage_start`** (Function) — `src/forensics/tui/pipeline_app.py:56`
- **`pipeline_stage_end`** (Function) — `src/forensics/tui/pipeline_app.py:60`
- **`fetch_progress`** (Function) — `src/forensics/tui/pipeline_app.py:70`
- **`pipeline_run_phase_start`** (Function) — `src/forensics/tui/pipeline_app.py:73`
- **`pipeline_run_phase_end`** (Function) — `src/forensics/tui/pipeline_app.py:76`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ForensicsSetupApp` | Class | `src/forensics/tui/app.py` | 30 |
| `TextualPipelineObserver` | Class | `src/forensics/tui/pipeline_app.py` | 43 |
| `pipeline_stage_start` | Function | `src/forensics/tui/pipeline_app.py` | 56 |
| `pipeline_stage_end` | Function | `src/forensics/tui/pipeline_app.py` | 60 |
| `fetch_progress` | Function | `src/forensics/tui/pipeline_app.py` | 70 |
| `pipeline_run_phase_start` | Function | `src/forensics/tui/pipeline_app.py` | 73 |
| `pipeline_run_phase_end` | Function | `src/forensics/tui/pipeline_app.py` | 76 |
| `on_mount` | Function | `src/forensics/tui/pipeline_app.py` | 123 |
| `on_worker_state_changed` | Function | `src/forensics/tui/pipeline_app.py` | 205 |
| `metadata_author_started` | Function | `src/forensics/tui/pipeline_app.py` | 64 |
| `metadata_author_done` | Function | `src/forensics/tui/pipeline_app.py` | 67 |
| `survey_author_started` | Function | `src/forensics/tui/pipeline_app.py` | 79 |
| `survey_author_finished` | Function | `src/forensics/tui/pipeline_app.py` | 84 |
| `test_tui_app_mounts` | Function | `tests/test_tui.py` | 134 |
| `main` | Function | `src/forensics/tui/__init__.py` | 14 |
| `setup_wizard` | Function | `src/forensics/cli/__init__.py` | 303 |
| `action_quit` | Function | `src/forensics/tui/pipeline_app.py` | 160 |
| `_dispatch` | Function | `src/forensics/tui/pipeline_app.py` | 53 |
| `_phase_widget` | Function | `src/forensics/tui/pipeline_app.py` | 226 |
| `_on_run_phase_start` | Function | `src/forensics/tui/pipeline_app.py` | 229 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Metadata_author_started → _ensure_author_row` | intra_community | 3 |
| `Metadata_author_done → _ensure_author_row` | intra_community | 3 |
| `Pipeline_run_phase_start → _phase_widget` | intra_community | 3 |
| `Pipeline_run_phase_start → _log_event` | intra_community | 3 |
| `Pipeline_run_phase_end → _phase_widget` | intra_community | 3 |
| `Pipeline_run_phase_end → _log_event` | intra_community | 3 |
| `Survey_author_started → _ensure_author_row` | intra_community | 3 |
| `Survey_author_finished → _ensure_author_row` | intra_community | 3 |
| `Setup_wizard → ForensicsSetupApp` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "pipeline_stage_start"})` — see callers and callees
2. `gitnexus_query({query: "tui"})` — find related execution flows
3. Read key files listed above for implementation details
