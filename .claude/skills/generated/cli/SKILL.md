---
name: cli
description: "Skill for the Cli area of mediaite-ghostink. 40 symbols across 11 files."
---

# Cli

40 symbols | 11 files | Cohesion: 66%

## When to Use

- Working with code in `src/`
- Understanding how from_settings, survey, get_cli_state work
- Modifying cli-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/cli/scrape.py` | scrape, _with_pipeline_stage, _discover_only, _metadata_only, _fetch_only (+9) |
| `src/forensics/cli/__init__.py` | _configure_logging, _root, run_all, dashboard_cmd, _settings_load_errors (+3) |
| `src/forensics/cli/analyze.py` | _write_run_metadata, _run_compare_only_flow, _resolve_mode_flags, _run_ai_baseline_stage, run_analyze (+1) |
| `src/forensics/cli/survey.py` | _survey_dry_run_echo, _survey_print_report, survey |
| `src/forensics/cli/state.py` | ForensicsCliState, get_cli_state |
| `src/forensics/cli/baseline.py` | run_ai_baseline_command, _run |
| `src/forensics/survey/qualification.py` | from_settings |
| `tests/test_preregistration.py` | test_run_analyze_invokes_verify_preregistration |
| `tests/unit/test_ensure_repo.py` | test_ensure_repo_yields_injected_repository |
| `src/forensics/scraper/fetcher.py` | fetch_articles |

## Entry Points

Start here when exploring this area:

- **`from_settings`** (Function) — `src/forensics/survey/qualification.py:33`
- **`survey`** (Function) — `src/forensics/cli/survey.py:82`
- **`get_cli_state`** (Function) — `src/forensics/cli/state.py:16`
- **`scrape`** (Function) — `src/forensics/cli/scrape.py:493`
- **`run_all`** (Function) — `src/forensics/cli/__init__.py:290`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ForensicsCliState` | Class | `src/forensics/cli/state.py` | 10 |
| `from_settings` | Function | `src/forensics/survey/qualification.py` | 33 |
| `survey` | Function | `src/forensics/cli/survey.py` | 82 |
| `get_cli_state` | Function | `src/forensics/cli/state.py` | 16 |
| `scrape` | Function | `src/forensics/cli/scrape.py` | 493 |
| `run_all` | Function | `src/forensics/cli/__init__.py` | 290 |
| `dashboard_cmd` | Function | `src/forensics/cli/__init__.py` | 313 |
| `test_run_analyze_invokes_verify_preregistration` | Function | `tests/test_preregistration.py` | 146 |
| `run_ai_baseline_command` | Function | `src/forensics/cli/baseline.py` | 17 |
| `run_analyze` | Function | `src/forensics/cli/analyze.py` | 174 |
| `analyze` | Function | `src/forensics/cli/analyze.py` | 268 |
| `test_ensure_repo_yields_injected_repository` | Function | `tests/unit/test_ensure_repo.py` | 10 |
| `fetch_articles` | Function | `src/forensics/scraper/fetcher.py` | 753 |
| `ensure_repo` | Function | `src/forensics/storage/repository.py` | 584 |
| `preflight` | Function | `src/forensics/cli/__init__.py` | 132 |
| `validate_config` | Function | `src/forensics/cli/__init__.py` | 195 |
| `_survey_dry_run_echo` | Function | `src/forensics/cli/survey.py` | 32 |
| `_survey_print_report` | Function | `src/forensics/cli/survey.py` | 52 |
| `_configure_logging` | Function | `src/forensics/cli/__init__.py` | 32 |
| `_root` | Function | `src/forensics/cli/__init__.py` | 52 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Survey → Parse_datetime` | cross_community | 7 |
| `Survey → Article` | cross_community | 7 |
| `Run_all → Config_fingerprint` | cross_community | 7 |
| `Run_ai_baseline_command → Factory` | cross_community | 7 |
| `Run_ai_baseline_command → Config_fingerprint` | cross_community | 7 |
| `Run_ai_baseline_command → Author` | cross_community | 7 |
| `Survey → Author` | cross_community | 6 |
| `Survey → _validate_batch_size` | cross_community | 6 |
| `Survey → _require_conn` | cross_community | 6 |
| `Scrape → Config_fingerprint` | cross_community | 6 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 29 calls |
| Analysis | 3 calls |
| Progress | 2 calls |
| Unit | 2 calls |
| Scraper | 1 calls |
| Survey | 1 calls |
| Storage | 1 calls |
| Integration | 1 calls |

## How to Explore

1. `gitnexus_context({name: "from_settings"})` — see callers and callees
2. `gitnexus_query({query: "cli"})` — find related execution flows
3. Read key files listed above for implementation details
