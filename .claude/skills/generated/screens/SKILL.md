---
name: screens
description: "Skill for the Screens area of mediaite-ghostink. 33 symbols across 7 files."
---

# Screens

33 symbols | 7 files | Cohesion: 92%

## When to Use

- Working with code in `src/`
- Understanding how test_dependency_check_returns_structured_results, test_dependency_check_detects_missing_spacy, test_dependency_check_has_blocking_failures_helper work
- Modifying screens-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/tui/screens/dependencies.py` | DependencyCheckResult, _check_python, _check_spacy_model, _check_sentence_transformers, _check_quarto (+6) |
| `src/forensics/tui/screens/config.py` | ConfigInputs, generate_config, write_config, _inputs_from_state, on_mount (+3) |
| `tests/test_tui.py` | test_dependency_check_returns_structured_results, test_dependency_check_detects_missing_spacy, test_dependency_check_has_blocking_failures_helper, test_config_generation_no_placeholders_blind, test_config_generation_no_placeholders_handpick (+2) |
| `src/forensics/tui/screens/preflight.py` | on_mount, _run_preflight, on_button_pressed |
| `src/forensics/tui/screens/launch.py` | on_button_pressed, _emit_and_exit |
| `src/forensics/tui/app.py` | action_next_step |
| `src/forensics/tui/screens/discovery.py` | on_button_pressed |

## Entry Points

Start here when exploring this area:

- **`test_dependency_check_returns_structured_results`** (Function) — `tests/test_tui.py:22`
- **`test_dependency_check_detects_missing_spacy`** (Function) — `tests/test_tui.py:36`
- **`test_dependency_check_has_blocking_failures_helper`** (Function) — `tests/test_tui.py:53`
- **`check_dependencies`** (Function) — `src/forensics/tui/screens/dependencies.py:173`
- **`has_blocking_failures`** (Function) — `src/forensics/tui/screens/dependencies.py:188`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `DependencyCheckResult` | Class | `src/forensics/tui/screens/dependencies.py` | 33 |
| `ConfigInputs` | Class | `src/forensics/tui/screens/config.py` | 23 |
| `test_dependency_check_returns_structured_results` | Function | `tests/test_tui.py` | 22 |
| `test_dependency_check_detects_missing_spacy` | Function | `tests/test_tui.py` | 36 |
| `test_dependency_check_has_blocking_failures_helper` | Function | `tests/test_tui.py` | 53 |
| `check_dependencies` | Function | `src/forensics/tui/screens/dependencies.py` | 173 |
| `has_blocking_failures` | Function | `src/forensics/tui/screens/dependencies.py` | 188 |
| `on_mount` | Function | `src/forensics/tui/screens/dependencies.py` | 207 |
| `test_config_generation_no_placeholders_blind` | Function | `tests/test_tui.py` | 76 |
| `test_config_generation_no_placeholders_handpick` | Function | `tests/test_tui.py` | 94 |
| `test_write_config_backs_up_existing` | Function | `tests/test_tui.py` | 110 |
| `test_write_config_no_backup_when_missing` | Function | `tests/test_tui.py` | 120 |
| `generate_config` | Function | `src/forensics/tui/screens/config.py` | 33 |
| `write_config` | Function | `src/forensics/tui/screens/config.py` | 124 |
| `on_mount` | Function | `src/forensics/tui/screens/config.py` | 179 |
| `on_button_pressed` | Function | `src/forensics/tui/screens/config.py` | 202 |
| `action_next_step` | Function | `src/forensics/tui/app.py` | 68 |
| `on_mount` | Function | `src/forensics/tui/screens/preflight.py` | 33 |
| `on_button_pressed` | Function | `src/forensics/tui/screens/preflight.py` | 68 |
| `on_button_pressed` | Function | `src/forensics/tui/screens/discovery.py` | 113 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `On_button_pressed → Config_fingerprint` | cross_community | 7 |
| `On_mount → Config_fingerprint` | cross_community | 7 |
| `On_button_pressed → ForensicsSettings` | cross_community | 6 |
| `On_mount → ForensicsSettings` | cross_community | 6 |
| `On_button_pressed → ConfigInputs` | intra_community | 5 |
| `On_button_pressed → Config_fingerprint` | cross_community | 5 |
| `On_button_pressed → PreflightCheck` | cross_community | 5 |
| `On_mount → PreflightCheck` | cross_community | 5 |
| `On_mount → ConfigInputs` | intra_community | 5 |
| `On_mount → DependencyCheckResult` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 4 calls |
| Features | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_dependency_check_returns_structured_results"})` — see callers and callees
2. `gitnexus_query({query: "screens"})` — find related execution flows
3. Read key files listed above for implementation details
