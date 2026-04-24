---
name: evals
description: "Skill for the Evals area of mediaite-ghostink. 14 symbols across 5 files."
---

# Evals

14 symbols | 5 files | Cohesion: 82%

## When to Use

- Working with code in `evals/`
- Understanding how test_make_baseline_agent_requires_pydantic_ai, main, make_baseline_agent work
- Modifying evals-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `evals/baseline_quality.py` | _run_model, _parser, _amain, main, BaselineInput (+5) |
| `tests/test_baseline.py` | test_make_baseline_agent_requires_pydantic_ai |
| `src/forensics/baseline/agent.py` | make_baseline_agent |
| `tests/evals/test_core_eval.py` | test_eval_cli_main_entrypoint_returns_int |
| `src/forensics/cli/__init__.py` | main |

## Entry Points

Start here when exploring this area:

- **`test_make_baseline_agent_requires_pydantic_ai`** (Function) — `tests/test_baseline.py:132`
- **`main`** (Function) — `evals/baseline_quality.py:235`
- **`make_baseline_agent`** (Function) — `src/forensics/baseline/agent.py:47`
- **`build_dataset`** (Function) — `evals/baseline_quality.py:99`
- **`test_eval_cli_main_entrypoint_returns_int`** (Function) — `tests/evals/test_core_eval.py:43`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `BaselineInput` | Class | `evals/baseline_quality.py` | 24 |
| `WordCountAccuracy` | Class | `evals/baseline_quality.py` | 49 |
| `TopicRelevance` | Class | `evals/baseline_quality.py` | 57 |
| `RepetitionDetector` | Class | `evals/baseline_quality.py` | 65 |
| `PerplexityRangeCheck` | Class | `evals/baseline_quality.py` | 78 |
| `test_make_baseline_agent_requires_pydantic_ai` | Function | `tests/test_baseline.py` | 132 |
| `main` | Function | `evals/baseline_quality.py` | 235 |
| `make_baseline_agent` | Function | `src/forensics/baseline/agent.py` | 47 |
| `build_dataset` | Function | `evals/baseline_quality.py` | 99 |
| `test_eval_cli_main_entrypoint_returns_int` | Function | `tests/evals/test_core_eval.py` | 43 |
| `main` | Function | `src/forensics/cli/__init__.py` | 406 |
| `_run_model` | Function | `evals/baseline_quality.py` | 146 |
| `_parser` | Function | `evals/baseline_quality.py` | 195 |
| `_amain` | Function | `evals/baseline_quality.py` | 203 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Config_fingerprint` | cross_community | 7 |
| `Main → ForensicsSettings` | cross_community | 5 |
| `Main → BaselineInput` | cross_community | 5 |
| `Main → WordCountAccuracy` | cross_community | 5 |
| `Main → TopicRelevance` | cross_community | 5 |
| `Main → RepetitionDetector` | cross_community | 5 |
| `Main → Make_baseline_agent` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 3 calls |

## How to Explore

1. `gitnexus_context({name: "test_make_baseline_agent_requires_pydantic_ai"})` — see callers and callees
2. `gitnexus_query({query: "evals"})` — find related execution flows
3. Read key files listed above for implementation details
