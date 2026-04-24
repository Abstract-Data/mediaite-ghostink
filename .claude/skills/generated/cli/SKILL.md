---
name: cli
description: "Skill for the Cli area of mediaite-ghostink. 49 symbols across 14 files."
---

# Cli

49 symbols | 14 files | Cohesion: 66%

## When to Use

- Working with code in `src/`
- Understanding how test_record_audit_optional_inserts_row, test_record_audit_optional_logs_on_oserror, test_record_audit_required_propagates work
- Modifying cli-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/cli/scrape.py` | scrape, _with_pipeline_stage, _discover_only, _metadata_only, _fetch_only (+9) |
| `src/forensics/cli/__init__.py` | _configure_logging, _root, run_all, dashboard_cmd, _settings_load_errors (+3) |
| `tests/test_pipeline_context.py` | test_record_audit_optional_inserts_row, test_record_audit_optional_logs_on_oserror, test_record_audit_required_propagates, test_record_audit_skips_row_when_fingerprint_none, test_resolve_accepts_explicit_root |
| `src/forensics/cli/analyze.py` | _write_run_metadata, _run_compare_only_flow, _resolve_mode_flags, run_analyze, analyze |
| `src/forensics/cli/survey.py` | _survey_dry_run_echo, _survey_print_report, survey |
| `scripts/lint_agents_md.py` | validate_agents_file, main |
| `src/forensics/pipeline_context.py` | resolve, record_audit |
| `src/forensics/cli/state.py` | ForensicsCliState, get_cli_state |
| `src/forensics/storage/repository.py` | rewrite_raw_paths_after_archive, ensure_repo |
| `src/forensics/scraper/fetcher.py` | archive_raw_year_dirs, fetch_articles |

## Entry Points

Start here when exploring this area:

- **`test_record_audit_optional_inserts_row`** (Function) — `tests/test_pipeline_context.py:11`
- **`test_record_audit_optional_logs_on_oserror`** (Function) — `tests/test_pipeline_context.py:36`
- **`test_record_audit_required_propagates`** (Function) — `tests/test_pipeline_context.py:57`
- **`test_record_audit_skips_row_when_fingerprint_none`** (Function) — `tests/test_pipeline_context.py:91`
- **`test_resolve_accepts_explicit_root`** (Function) — `tests/test_pipeline_context.py:124`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ForensicsCliState` | Class | `src/forensics/cli/state.py` | 10 |
| `test_record_audit_optional_inserts_row` | Function | `tests/test_pipeline_context.py` | 11 |
| `test_record_audit_optional_logs_on_oserror` | Function | `tests/test_pipeline_context.py` | 36 |
| `test_record_audit_required_propagates` | Function | `tests/test_pipeline_context.py` | 57 |
| `test_record_audit_skips_row_when_fingerprint_none` | Function | `tests/test_pipeline_context.py` | 91 |
| `test_resolve_accepts_explicit_root` | Function | `tests/test_pipeline_context.py` | 124 |
| `validate_agents_file` | Function | `scripts/lint_agents_md.py` | 31 |
| `main` | Function | `scripts/lint_agents_md.py` | 62 |
| `resolve` | Function | `src/forensics/pipeline_context.py` | 24 |
| `record_audit` | Function | `src/forensics/pipeline_context.py` | 33 |
| `report` | Function | `src/forensics/cli/report.py` | 15 |
| `extract` | Function | `src/forensics/cli/extract.py` | 16 |
| `run_analyze` | Function | `src/forensics/cli/analyze.py` | 154 |
| `analyze` | Function | `src/forensics/cli/analyze.py` | 247 |
| `from_settings` | Function | `src/forensics/survey/qualification.py` | 33 |
| `survey` | Function | `src/forensics/cli/survey.py` | 82 |
| `get_cli_state` | Function | `src/forensics/cli/state.py` | 16 |
| `scrape` | Function | `src/forensics/cli/scrape.py` | 493 |
| `run_all` | Function | `src/forensics/cli/__init__.py` | 290 |
| `dashboard_cmd` | Function | `src/forensics/cli/__init__.py` | 313 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Generate → Config_fingerprint` | cross_community | 8 |
| `Survey → Parse_datetime` | cross_community | 7 |
| `Survey → Article` | cross_community | 7 |
| `Report → _connect` | cross_community | 7 |
| `Lock_preregistration_cmd → Config_fingerprint` | cross_community | 7 |
| `Export_data → _project_root` | cross_community | 7 |
| `Run_all → Config_fingerprint` | cross_community | 7 |
| `On_button_pressed → Config_fingerprint` | cross_community | 7 |
| `Main → Config_fingerprint` | cross_community | 7 |
| `Main → Config_fingerprint` | cross_community | 7 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 29 calls |
| Forensics | 6 calls |
| Analysis | 3 calls |
| Scraper | 2 calls |
| Progress | 2 calls |
| Survey | 1 calls |
| Storage | 1 calls |
| Integration | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_record_audit_optional_inserts_row"})` — see callers and callees
2. `gitnexus_query({query: "cli"})` — find related execution flows
3. Read key files listed above for implementation details
