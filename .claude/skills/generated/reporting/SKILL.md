---
name: reporting
description: "Skill for the Reporting area of mediaite-ghostink. 21 symbols across 7 files."
---

# Reporting

21 symbols | 7 files | Cohesion: 66%

## When to Use

- Working with code in `src/`
- Understanding how test_narrative_caveat_always_present, generate_evidence_narrative, test_corpus_custody_verify work
- Modifying reporting-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/reporting/narrative.py` | _preregistration_clause, _convergence_sentences, _effect_size_sentences, _change_point_sentences, _control_sentences (+3) |
| `src/forensics/reporting/__init__.py` | _legacy_db_artifact_ok, _quarto_bin, _validate_report_prerequisites, _prepare_report_env, _render_full_book (+1) |
| `tests/test_report.py` | test_corpus_custody_verify, test_quarto_bin_delegates_to_which |
| `src/forensics/utils/provenance.py` | load_corpus_custody, verify_corpus_hash |
| `tests/test_narrative.py` | test_narrative_caveat_always_present |
| `src/forensics/storage/json_io.py` | ensure_dir |
| `src/forensics/features/pipeline.py` | _archive_embeddings_if_mismatch |

## Entry Points

Start here when exploring this area:

- **`test_narrative_caveat_always_present`** (Function) — `tests/test_narrative.py:187`
- **`generate_evidence_narrative`** (Function) — `src/forensics/reporting/narrative.py:177`
- **`test_corpus_custody_verify`** (Function) — `tests/test_report.py:160`
- **`test_quarto_bin_delegates_to_which`** (Function) — `tests/test_report.py:289`
- **`load_corpus_custody`** (Function) — `src/forensics/utils/provenance.py:157`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_narrative_caveat_always_present` | Function | `tests/test_narrative.py` | 187 |
| `generate_evidence_narrative` | Function | `src/forensics/reporting/narrative.py` | 177 |
| `test_corpus_custody_verify` | Function | `tests/test_report.py` | 160 |
| `test_quarto_bin_delegates_to_which` | Function | `tests/test_report.py` | 289 |
| `load_corpus_custody` | Function | `src/forensics/utils/provenance.py` | 157 |
| `verify_corpus_hash` | Function | `src/forensics/utils/provenance.py` | 168 |
| `ensure_dir` | Function | `src/forensics/storage/json_io.py` | 27 |
| `run_report` | Function | `src/forensics/reporting/__init__.py` | 127 |
| `_preregistration_clause` | Function | `src/forensics/reporting/narrative.py` | 43 |
| `_convergence_sentences` | Function | `src/forensics/reporting/narrative.py` | 70 |
| `_effect_size_sentences` | Function | `src/forensics/reporting/narrative.py` | 88 |
| `_change_point_sentences` | Function | `src/forensics/reporting/narrative.py` | 119 |
| `_control_sentences` | Function | `src/forensics/reporting/narrative.py` | 133 |
| `_score_sentences` | Function | `src/forensics/reporting/narrative.py` | 145 |
| `_caveat_sentence` | Function | `src/forensics/reporting/narrative.py` | 164 |
| `_legacy_db_artifact_ok` | Function | `src/forensics/reporting/__init__.py` | 23 |
| `_quarto_bin` | Function | `src/forensics/reporting/__init__.py` | 30 |
| `_validate_report_prerequisites` | Function | `src/forensics/reporting/__init__.py` | 53 |
| `_prepare_report_env` | Function | `src/forensics/reporting/__init__.py` | 47 |
| `_render_full_book` | Function | `src/forensics/reporting/__init__.py` | 104 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Report → _collect_hash_enumerated_fields` | cross_community | 8 |
| `Report → _connect` | cross_community | 7 |
| `Report → Config_fingerprint` | cross_community | 6 |
| `Analyze → _connect` | cross_community | 6 |
| `Report → Load_corpus_custody` | cross_community | 5 |
| `Report → ForensicsSettings` | cross_community | 4 |
| `Report → _legacy_db_artifact_ok` | cross_community | 4 |
| `Report → _quarto_bin` | cross_community | 4 |
| `Analyze → Load_corpus_custody` | cross_community | 4 |
| `_run → Ensure_dir` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 5 calls |
| Unit | 2 calls |
| Survey | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_narrative_caveat_always_present"})` — see callers and callees
2. `gitnexus_query({query: "reporting"})` — find related execution flows
3. Read key files listed above for implementation details
