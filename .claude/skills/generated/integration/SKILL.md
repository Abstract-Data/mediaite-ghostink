---
name: integration
description: "Skill for the Integration area of mediaite-ghostink. 35 symbols across 7 files."
---

# Integration

35 symbols | 7 files | Cohesion: 80%

## When to Use

- Working with code in `tests/`
- Understanding how test_scrape_dry_run_requires_fetch, test_scrape_archive_only, test_scrape_dedup_only work
- Modifying integration-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/integration/test_cli.py` | _plain_help, test_scrape_help_lists_flags, test_extract_help_lists_flags, test_analyze_help_lists_flags, test_report_help_lists_flags (+7) |
| `tests/integration/test_cli_scrape_dispatch.py` | test_scrape_dry_run_requires_fetch, test_scrape_archive_only, test_scrape_dedup_only, test_scrape_fetch_only_dry_run, test_scrape_unsupported_flags (+5) |
| `tests/integration/test_duckdb_export.py` | _write_feature_shard, test_export_to_duckdb_creates_file_with_core_tables, test_export_to_duckdb_includes_feature_shards, test_export_to_duckdb_overwrites_existing_output, test_export_to_duckdb_requires_existing_sqlite |
| `src/forensics/storage/duckdb_queries.py` | ExportReport, export_to_duckdb, _collect_analysis_rows, _register_analysis_results |
| `src/forensics/cli/scrape.py` | _resolve_scrape_mode, dispatch_scrape |
| `src/forensics/cli/_helpers.py` | guard_placeholder_authors |
| `src/forensics/cli/__init__.py` | export_data |

## Entry Points

Start here when exploring this area:

- **`test_scrape_dry_run_requires_fetch`** (Function) — `tests/integration/test_cli_scrape_dispatch.py:15`
- **`test_scrape_archive_only`** (Function) — `tests/integration/test_cli_scrape_dispatch.py:34`
- **`test_scrape_dedup_only`** (Function) — `tests/integration/test_cli_scrape_dispatch.py:62`
- **`test_scrape_fetch_only_dry_run`** (Function) — `tests/integration/test_cli_scrape_dispatch.py:90`
- **`test_scrape_unsupported_flags`** (Function) — `tests/integration/test_cli_scrape_dispatch.py:118`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ExportReport` | Class | `src/forensics/storage/duckdb_queries.py` | 182 |
| `test_scrape_dry_run_requires_fetch` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 15 |
| `test_scrape_archive_only` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 34 |
| `test_scrape_dedup_only` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 62 |
| `test_scrape_fetch_only_dry_run` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 90 |
| `test_scrape_unsupported_flags` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 118 |
| `test_scrape_discover_only_zero_authors` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 137 |
| `test_scrape_metadata_only_missing_manifest` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 164 |
| `test_scrape_discover_placeholder_ok_with_all_authors` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 197 |
| `test_scrape_rejects_placeholder_template_authors` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 227 |
| `test_scrape_dispatch_rejects_partial_post_year_cli` | Function | `tests/integration/test_cli_scrape_dispatch.py` | 250 |
| `dispatch_scrape` | Function | `src/forensics/cli/scrape.py` | 419 |
| `guard_placeholder_authors` | Function | `src/forensics/cli/_helpers.py` | 15 |
| `test_scrape_help_lists_flags` | Function | `tests/integration/test_cli.py` | 31 |
| `test_extract_help_lists_flags` | Function | `tests/integration/test_cli.py` | 48 |
| `test_analyze_help_lists_flags` | Function | `tests/integration/test_cli.py` | 62 |
| `test_report_help_lists_flags` | Function | `tests/integration/test_cli.py` | 80 |
| `test_validate_help` | Function | `tests/integration/test_cli.py` | 149 |
| `test_export_help` | Function | `tests/integration/test_cli.py` | 196 |
| `test_survey_help_lists_flags` | Function | `tests/integration/test_cli.py` | 243 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Export_data → _project_root` | cross_community | 7 |
| `Scrape → Config_fingerprint` | cross_community | 6 |
| `Export_data → Config_fingerprint` | cross_community | 5 |
| `Scrape → ForensicsSettings` | cross_community | 4 |
| `Export_data → _sql_string_literal` | cross_community | 4 |
| `_run → ForensicsSettings` | cross_community | 4 |
| `Scrape → Resolve_posts_year_window` | cross_community | 3 |
| `Scrape → Guard_placeholder_authors` | cross_community | 3 |
| `Export_data → Ensure_parent` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 7 calls |
| Cli | 4 calls |
| Unit | 2 calls |
| Storage | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_scrape_dry_run_requires_fetch"})` — see callers and callees
2. `gitnexus_query({query: "integration"})` — find related execution flows
3. Read key files listed above for implementation details
