---
name: features
description: "Skill for the Features area of mediaite-ghostink. 80 symbols across 20 files."
---

# Features

80 symbols | 20 files | Cohesion: 77%

## When to Use

- Working with code in `src/`
- Understanding how test_ttr_calculation, test_mattr_window, test_hapax_ratio work
- Modifying features-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_features.py` | test_ttr_calculation, test_mattr_window, test_hapax_ratio, test_ai_marker_detection, test_nan_handling (+14) |
| `src/forensics/features/lexical.py` | _alphabetic_words, _ttr, _mattr, _hapax_ratio, _yules_k (+4) |
| `src/forensics/features/content.py` | _shannon_bigrams_trigrams, entropy_ngrams, _formula_score, _first_person_ratio, _hedging_frequency (+4) |
| `src/forensics/features/pipeline.py` | _load_spacy_model, _recent_peer_texts, _extract_features_for_article, _AuthorBatchResult, _write_author_embedding_artifacts (+2) |
| `src/forensics/features/pos_patterns.py` | _token_depth_to_root, max_dep_depth_sentence, dep_depth_per_sentence, _entropy_from_counts, extract_pos_pattern_features |
| `src/forensics/features/probability.py` | resolve_torch_device, load_reference_model, clear_model_cache, load |
| `src/forensics/features/probability_pipeline.py` | _model_card_payload, _filter_articles, _transformers_version, extract_probability_features |
| `tests/test_probability.py` | test_load_binoculars_disabled_returns_none, test_real_gpt2_perplexity_smoke, eval |
| `src/forensics/utils/model_cache.py` | get_or_load, KeyedModelCache, clear |
| `src/forensics/features/binoculars.py` | load_binoculars_models, clear_pair_cache, load |

## Entry Points

Start here when exploring this area:

- **`test_ttr_calculation`** (Function) — `tests/test_features.py:34`
- **`test_mattr_window`** (Function) — `tests/test_features.py:43`
- **`test_hapax_ratio`** (Function) — `tests/test_features.py:54`
- **`test_ai_marker_detection`** (Function) — `tests/test_features.py:65`
- **`test_nan_handling`** (Function) — `tests/test_features.py:416`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PosShapeFeatures` | Class | `src/forensics/models/features.py` | 75 |
| `KeyedModelCache` | Class | `src/forensics/utils/model_cache.py` | 10 |
| `test_ttr_calculation` | Function | `tests/test_features.py` | 34 |
| `test_mattr_window` | Function | `tests/test_features.py` | 43 |
| `test_hapax_ratio` | Function | `tests/test_features.py` | 54 |
| `test_ai_marker_detection` | Function | `tests/test_features.py` | 65 |
| `test_nan_handling` | Function | `tests/test_features.py` | 416 |
| `extract_lexical_features` | Function | `src/forensics/features/lexical.py` | 174 |
| `test_bigram_entropy` | Function | `tests/test_features.py` | 136 |
| `test_self_similarity` | Function | `tests/test_features.py` | 150 |
| `test_self_similarity_ignores_blank_peers` | Function | `tests/test_features.py` | 162 |
| `test_content_features_regression_values` | Function | `tests/test_features.py` | 174 |
| `entropy_ngrams` | Function | `src/forensics/features/content.py` | 42 |
| `extract_content_features` | Function | `src/forensics/features/content.py` | 216 |
| `test_load_binoculars_disabled_returns_none` | Function | `tests/test_probability.py` | 183 |
| `test_real_gpt2_perplexity_smoke` | Function | `tests/test_probability.py` | 324 |
| `factory` | Function | `tests/test_analysis_infrastructure.py` | 17 |
| `evaluate` | Function | `evals/baseline_quality.py` | 82 |
| `get_or_load` | Function | `src/forensics/utils/model_cache.py` | 18 |
| `resolve_torch_device` | Function | `src/forensics/features/probability.py` | 38 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_ai_baseline_command → Factory` | cross_community | 7 |
| `Evaluate → _FakeTensor` | cross_community | 5 |
| `Extract_content_features → Encode` | cross_community | 5 |
| `Run_ai_baseline_command → Encode` | cross_community | 5 |
| `Run_ai_baseline_command → Ensure_parent` | cross_community | 5 |
| `_extract_features_for_article → _token_depth_to_root` | cross_community | 5 |
| `Extract_probability_features → Author` | cross_community | 4 |
| `Extract_probability_features → Factory` | cross_community | 4 |
| `Evaluate → Factory` | intra_community | 4 |
| `Evaluate → Size` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 12 calls |
| Unit | 3 calls |
| Scraper | 2 calls |
| Storage | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_ttr_calculation"})` — see callers and callees
2. `gitnexus_query({query: "features"})` — find related execution flows
3. Read key files listed above for implementation details
