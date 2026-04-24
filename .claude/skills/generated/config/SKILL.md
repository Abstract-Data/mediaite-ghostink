---
name: config
description: "Skill for the Config area of mediaite-ghostink. 4 symbols across 1 files."
---

# Config

4 symbols | 1 files | Cohesion: 67%

## When to Use

- Working with code in `src/`
- Understanding how db_path, settings_customise_sources work
- Modifying config-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/config/settings.py` | _project_root, _config_toml_path, db_path, settings_customise_sources |

## Entry Points

Start here when exploring this area:

- **`db_path`** (Function) — `src/forensics/config/settings.py:297`
- **`settings_customise_sources`** (Function) — `src/forensics/config/settings.py:302`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `db_path` | Function | `src/forensics/config/settings.py` | 297 |
| `settings_customise_sources` | Function | `src/forensics/config/settings.py` | 302 |
| `_project_root` | Function | `src/forensics/config/settings.py` | 23 |
| `_config_toml_path` | Function | `src/forensics/config/settings.py` | 36 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Generate → Config_fingerprint` | cross_community | 8 |
| `Lock_preregistration_cmd → Config_fingerprint` | cross_community | 7 |
| `Export_data → _project_root` | cross_community | 7 |
| `Run_all → Config_fingerprint` | cross_community | 7 |
| `On_button_pressed → Config_fingerprint` | cross_community | 7 |
| `Main → Config_fingerprint` | cross_community | 7 |
| `Main → Config_fingerprint` | cross_community | 7 |
| `Run_ai_baseline_command → Config_fingerprint` | cross_community | 7 |
| `On_mount → Config_fingerprint` | cross_community | 7 |
| `_thread_pipeline → Config_fingerprint` | cross_community | 7 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cli | 2 calls |

## How to Explore

1. `gitnexus_context({name: "db_path"})` — see callers and callees
2. `gitnexus_query({query: "config"})` — find related execution flows
3. Read key files listed above for implementation details
