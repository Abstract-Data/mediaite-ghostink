---
name: features
description: "Skill for the Features area of mediaite-ghostink. 83 symbols across 20 files."
---

# Features

83 symbols | 20 files | Cohesion: 76%

## When to Use

- Working with code in `src/`
- Understanding how test_ttr_calculation, test_mattr_window, test_hapax_ratio work
- Modifying features-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_features.py` | test_ttr_calculation, test_mattr_window, test_hapax_ratio, test_ai_marker_detection, test_nan_handling (+14) |
| `src/forensics/features/lexical.py` | _alphabetic_words, _ttr, _mattr, _hapax_ratio, _yules_k (+4) |
| `src/forensics/features/pipeline.py` | _load_spacy_model, _recent_peer_texts, _extract_features_for_article, clear_spacy_model_cache, _AuthorBatchResult (+4) |
| `src/forensics/features/content.py` | _shannon_bigrams_trigrams, entropy_ngrams, _formula_score, _first_person_ratio, _hedging_frequency (+4) |
| `src/forensics/features/pos_patterns.py` | _token_depth_to_root, max_dep_depth_sentence, dep_depth_per_sentence, _entropy_from_counts, extract_pos_pattern_features |
| `src/forensics/features/probability.py` | resolve_torch_device, load_reference_model, clear_model_cache, load |
| `src/forensics/features/structural.py` | _sentence_word_counts, _paragraphs, _passive_sentence, extract_structural_features |
| `src/forensics/features/probability_pipeline.py` | _model_card_payload, _filter_articles, _transformers_version, extract_probability_features |
| `tests/test_probability.py` | test_load_binoculars_disabled_returns_none, test_real_gpt2_perplexity_smoke, eval |
| `src/forensics/utils/model_cache.py` | get_or_load, KeyedModelCache, clear |

## Entry Points

Start here when exploring this area:

- **`test_ttr_calculation`** (Function) — `tests/test_features.py:34`
- **`test_mattr_window`** (Function) — `tests/test_features.py:43`
- **`test_hapax_ratio`** (Function) — `tests/test_features.py:54`
- **`test_ai_marker_detection`** (Function) — `tests/test_features.py:65`
- **`test_nan_handling`** (Function) — `tests/test_features.py:398`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PosShapeFeatures` | Class | `src/forensics/models/features.py` | 75 |
| `KeyedModelCache` | Class | `src/forensics/utils/model_cache.py` | 10 |
| `test_ttr_calculation` | Function | `tests/test_features.py` | 34 |
| `test_mattr_window` | Function | `tests/test_features.py` | 43 |
| `test_hapax_ratio` | Function | `tests/test_features.py` | 54 |
| `test_ai_marker_detection` | Function | `tests/test_features.py` | 65 |
| `test_nan_handling` | Function | `tests/test_features.py` | 398 |
| `extract_lexical_features` | Function | `src/forensics/features/lexical.py` | 174 |
| `test_load_binoculars_disabled_returns_none` | Function | `tests/test_probability.py` | 183 |
| `test_real_gpt2_perplexity_smoke` | Function | `tests/test_probability.py` | 324 |
| `factory` | Function | `tests/test_analysis_infrastructure.py` | 17 |
| `evaluate` | Function | `evals/baseline_quality.py` | 82 |
| `get_or_load` | Function | `src/forensics/utils/model_cache.py` | 18 |
| `resolve_torch_device` | Function | `src/forensics/features/probability.py` | 38 |
| `load_reference_model` | Function | `src/forensics/features/probability.py` | 49 |
| `load_binoculars_models` | Function | `src/forensics/features/binoculars.py` | 24 |
| `test_pos_bigram_extraction` | Function | `tests/test_features.py` | 74 |
| `test_pos_bigram_normalization` | Function | `tests/test_features.py` | 82 |
| `test_clause_initial_entropy` | Function | `tests/test_features.py` | 91 |
| `test_dep_depth_known_sentence` | Function | `tests/test_features.py` | 101 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_ai_baseline_command → Factory` | cross_community | 7 |
| `Evaluate → _FakeTensor` | cross_community | 5 |
| `Extract_content_features → Encode` | cross_community | 5 |
| `_extract_features_for_article → _token_depth_to_root` | cross_community | 5 |
| `Extract_probability_features → Author` | cross_community | 4 |
| `Extract_probability_features → Factory` | cross_community | 4 |
| `Evaluate → Factory` | intra_community | 4 |
| `Evaluate → Size` | cross_community | 4 |
| `Extract_content_features → _self_similarity_tfidf_mean` | cross_community | 4 |
| `Write_features → ForensicsSettings` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 12 calls |
| Storage | 4 calls |
| Unit | 3 calls |
| Progress | 2 calls |
| Scraper | 1 calls |
| Forensics | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_ttr_calculation"})` — see callers and callees
2. `gitnexus_query({query: "features"})` — find related execution flows
3. Read key files listed above for implementation details
