---
name: reporting
description: "Skill for the Reporting area of mediaite-ghostink. 14 symbols across 5 files."
---

# Reporting

14 symbols | 5 files | Cohesion: 64%

## When to Use

- Working with code in `src/`
- Understanding how test_narrative_caveat_always_present, generate_evidence_narrative, ensure_dir work
- Modifying reporting-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/reporting/narrative.py` | _preregistration_clause, _convergence_sentences, _effect_size_sentences, _change_point_sentences, _control_sentences (+3) |
| `src/forensics/reporting/__init__.py` | _prepare_report_env, _render_full_book, run_report |
| `tests/test_narrative.py` | test_narrative_caveat_always_present |
| `src/forensics/storage/json_io.py` | ensure_dir |
| `src/forensics/features/pipeline.py` | _archive_embeddings_if_mismatch |

## Entry Points

Start here when exploring this area:

- **`test_narrative_caveat_always_present`** (Function) — `tests/test_narrative.py:187`
- **`generate_evidence_narrative`** (Function) — `src/forensics/reporting/narrative.py:177`
- **`ensure_dir`** (Function) — `src/forensics/storage/json_io.py:27`
- **`run_report`** (Function) — `src/forensics/reporting/__init__.py:122`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_narrative_caveat_always_present` | Function | `tests/test_narrative.py` | 187 |
| `generate_evidence_narrative` | Function | `src/forensics/reporting/narrative.py` | 177 |
| `ensure_dir` | Function | `src/forensics/storage/json_io.py` | 27 |
| `run_report` | Function | `src/forensics/reporting/__init__.py` | 122 |
| `_preregistration_clause` | Function | `src/forensics/reporting/narrative.py` | 43 |
| `_convergence_sentences` | Function | `src/forensics/reporting/narrative.py` | 70 |
| `_effect_size_sentences` | Function | `src/forensics/reporting/narrative.py` | 88 |
| `_change_point_sentences` | Function | `src/forensics/reporting/narrative.py` | 119 |
| `_control_sentences` | Function | `src/forensics/reporting/narrative.py` | 133 |
| `_score_sentences` | Function | `src/forensics/reporting/narrative.py` | 145 |
| `_caveat_sentence` | Function | `src/forensics/reporting/narrative.py` | 164 |
| `_prepare_report_env` | Function | `src/forensics/reporting/__init__.py` | 46 |
| `_render_full_book` | Function | `src/forensics/reporting/__init__.py` | 99 |
| `_archive_embeddings_if_mismatch` | Function | `src/forensics/features/pipeline.py` | 95 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Report → _connect` | cross_community | 7 |
| `Report → Config_fingerprint` | cross_community | 6 |
| `Report → Load_corpus_custody` | cross_community | 5 |
| `Report → ForensicsSettings` | cross_community | 4 |
| `Report → _analysis_artifacts_ok` | cross_community | 4 |
| `Report → _quarto_bin` | cross_community | 4 |
| `_run → Ensure_dir` | cross_community | 4 |
| `Report → Ensure_dir` | cross_community | 3 |
| `Generate_evidence_narrative → _pipeline_a_score` | cross_community | 3 |
| `Generate_evidence_narrative → _pipeline_b_score` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 4 calls |
| Survey | 1 calls |
| Unit | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_narrative_caveat_always_present"})` — see callers and callees
2. `gitnexus_query({query: "reporting"})` — find related execution flows
3. Read key files listed above for implementation details
