---
name: baseline
description: "Skill for the Baseline area of mediaite-ghostink. 30 symbols across 9 files."
---

# Baseline

30 symbols | 9 files | Cohesion: 75%

## When to Use

- Working with code in `src/`
- Understanding how test_sanitize_model_tag_handles_colon_and_slash, test_hash_prompt_text_deterministic, test_cycle_keywords_round_robins work
- Modifying baseline-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_baseline.py` | test_sanitize_model_tag_handles_colon_and_slash, test_hash_prompt_text_deterministic, test_cycle_keywords_round_robins, test_cycle_keywords_empty_falls_back_to_default, test_generated_article_autofills_word_count (+4) |
| `src/forensics/baseline/prompts.py` | PromptContext, build_prompt, _templates_dir, load_template, list_templates |
| `src/forensics/baseline/utils.py` | sanitize_model_tag, get_model_digest, hash_prompt_text, dump_manifest |
| `src/forensics/baseline/orchestrator.py` | _cell_dir, _article_record, run_generation_matrix |
| `src/forensics/baseline/agent.py` | GeneratedArticle, with_auto_word_count, BaselineDeps |
| `src/forensics/cli/baseline.py` | run_ai_baseline_command, _run |
| `evals/baseline_quality.py` | BaselineOutput, generate |
| `src/forensics/baseline/topics.py` | cycle_keywords |
| `src/forensics/cli/analyze.py` | _run_ai_baseline_stage |

## Entry Points

Start here when exploring this area:

- **`test_sanitize_model_tag_handles_colon_and_slash`** (Function) — `tests/test_baseline.py:25`
- **`test_hash_prompt_text_deterministic`** (Function) — `tests/test_baseline.py:30`
- **`test_cycle_keywords_round_robins`** (Function) — `tests/test_baseline.py:78`
- **`test_cycle_keywords_empty_falls_back_to_default`** (Function) — `tests/test_baseline.py:83`
- **`test_generated_article_autofills_word_count`** (Function) — `tests/test_baseline.py:127`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `GeneratedArticle` | Class | `src/forensics/baseline/agent.py` | 26 |
| `BaselineOutput` | Class | `evals/baseline_quality.py` | 31 |
| `PromptContext` | Class | `src/forensics/baseline/prompts.py` | 13 |
| `BaselineDeps` | Class | `src/forensics/baseline/agent.py` | 15 |
| `test_sanitize_model_tag_handles_colon_and_slash` | Function | `tests/test_baseline.py` | 25 |
| `test_hash_prompt_text_deterministic` | Function | `tests/test_baseline.py` | 30 |
| `test_cycle_keywords_round_robins` | Function | `tests/test_baseline.py` | 78 |
| `test_cycle_keywords_empty_falls_back_to_default` | Function | `tests/test_baseline.py` | 83 |
| `test_generated_article_autofills_word_count` | Function | `tests/test_baseline.py` | 127 |
| `test_run_generation_matrix_dry_run_writes_plan` | Function | `tests/test_baseline.py` | 332 |
| `sanitize_model_tag` | Function | `src/forensics/baseline/utils.py` | 11 |
| `get_model_digest` | Function | `src/forensics/baseline/utils.py` | 16 |
| `hash_prompt_text` | Function | `src/forensics/baseline/utils.py` | 39 |
| `dump_manifest` | Function | `src/forensics/baseline/utils.py` | 44 |
| `cycle_keywords` | Function | `src/forensics/baseline/topics.py` | 111 |
| `run_generation_matrix` | Function | `src/forensics/baseline/orchestrator.py` | 76 |
| `with_auto_word_count` | Function | `src/forensics/baseline/agent.py` | 41 |
| `run_ai_baseline_command` | Function | `src/forensics/cli/baseline.py` | 17 |
| `test_build_prompt_renders_keywords_and_word_count` | Function | `tests/test_baseline.py` | 38 |
| `test_build_prompt_missing_template` | Function | `tests/test_baseline.py` | 58 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Generate → Config_fingerprint` | cross_community | 8 |
| `Main → Config_fingerprint` | cross_community | 7 |
| `Main → Author` | cross_community | 7 |
| `Main → _validate_batch_size` | cross_community | 7 |
| `Run_ai_baseline_command → Factory` | cross_community | 7 |
| `Run_ai_baseline_command → Config_fingerprint` | cross_community | 7 |
| `Run_ai_baseline_command → Author` | cross_community | 7 |
| `Main → ForensicsSettings` | cross_community | 6 |
| `Main → _require_conn` | cross_community | 6 |
| `Run_ai_baseline_command → ForensicsSettings` | cross_community | 6 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 8 calls |
| Scraper | 1 calls |
| Evals | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_sanitize_model_tag_handles_colon_and_slash"})` — see callers and callees
2. `gitnexus_query({query: "baseline"})` — find related execution flows
3. Read key files listed above for implementation details
