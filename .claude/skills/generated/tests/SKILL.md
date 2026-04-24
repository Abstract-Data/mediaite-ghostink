---
name: tests
description: "Skill for the Tests area of mediaite-ghostink. 467 symbols across 91 files."
---

# Tests

467 symbols | 91 files | Cohesion: 73%

## When to Use

- Working with code in `tests/`
- Understanding how test_insert_analysis_run_persists_row, test_init_db_creates_tables, test_upsert_author_round_trip work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/storage/repository.py` | UnfetchedUrl, _author_row_to_model, _validate_batch_size, _row_to_article, RepositoryReader (+23) |
| `tests/test_probability.py` | test_extract_probability_features_writes_parquet_and_model_card, _FakeTensor, size, clone, __call__ (+22) |
| `tests/test_scraper.py` | test_parse_wp_datetime_naive_becomes_utc, test_parse_wp_datetime_z_suffix, test_wp_post_to_article, test_article_url_exists_and_duplicate_skip, test_list_unfetched_resumability (+20) |
| `tests/test_report.py` | test_analysis_artifacts_ok_multiple_authors, test_report_config_validation, test_notebook_imports, test_quarto_config_exists, test_index_qmd_exists (+16) |
| `tests/test_parquet_embeddings_duckdb.py` | test_get_rolling_and_monthly_stats_with_sqlite_and_parquet, test_write_author_embedding_batch_shape_validation, test_write_author_embedding_batch_npz_roundtrip_no_pickle, test_unpack_article_ids_length_mismatch_raises, test_load_article_embeddings_legacy_npy_and_batch_npz (+12) |
| `tests/test_calibration.py` | _seed_db_with_author, _make_author, _make_article, _make_ai_article, _make_analysis (+10) |
| `tests/test_fetcher_phase_a.py` | test_parallel_fetches_complete_all_tasks, test_discover_authors_post_count_calls_overlap, _article_html_ctx, test_fetch_http_error_persists_placeholder, test_fetch_off_domain_persists_redirect_marker (+9) |
| `tests/test_survey.py` | _make_author, _make_article, _seed, test_qualification_filters_by_volume, test_qualification_filters_by_date_range (+9) |
| `tests/test_analysis.py` | test_extract_lda_topic_keywords_runs, test_bocpd_gradual_shift, _detect_bocpd_scalar_reference, test_bocpd_vectorized_matches_reference, test_bocpd_long_signal_runs_quickly (+8) |
| `tests/test_baseline.py` | test_sample_word_counts_uses_corpus, test_corpus_hash_deterministic, test_verify_corpus_hash_detects_mismatch, _seed_baseline_corpus, test_reembed_existing_baseline_roundtrips (+6) |

## Entry Points

Start here when exploring this area:

- **`test_insert_analysis_run_persists_row`** (Function) — `tests/test_storage.py:13`
- **`test_init_db_creates_tables`** (Function) — `tests/test_storage.py:30`
- **`test_upsert_author_round_trip`** (Function) — `tests/test_storage.py:46`
- **`test_upsert_article_and_query`** (Function) — `tests/test_storage.py:54`
- **`test_export_articles_jsonl_round_trip`** (Function) — `tests/test_storage.py:65`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `UnfetchedUrl` | Class | `src/forensics/storage/repository.py` | 32 |
| `RepositoryReader` | Class | `src/forensics/storage/repository.py` | 199 |
| `Repository` | Class | `src/forensics/storage/repository.py` | 357 |
| `Author` | Class | `src/forensics/models/author.py` | 21 |
| `Article` | Class | `src/forensics/models/article.py` | 12 |
| `AuthorDiscoveryResult` | Class | `src/forensics/tui/screens/discovery.py` | 22 |
| `RecordingObserver` | Class | `tests/test_pipeline_progress.py` | 15 |
| `AuthorManifest` | Class | `src/forensics/models/author.py` | 11 |
| `AuthorConfig` | Class | `src/forensics/config/settings.py` | 43 |
| `ForensicsSettings` | Class | `src/forensics/config/settings.py` | 273 |
| `AnalysisConfig` | Class | `src/forensics/config/settings.py` | 86 |
| `FeaturesConfig` | Class | `src/forensics/config/settings.py` | 204 |
| `QualificationCriteria` | Class | `src/forensics/survey/qualification.py` | 18 |
| `QualifiedAuthor` | Class | `src/forensics/survey/qualification.py` | 45 |
| `PreflightReport` | Class | `src/forensics/preflight.py` | 46 |
| `UnfetchedArticle` | Class | `src/forensics/storage/repository.py` | 39 |
| `ScrapingConfig` | Class | `src/forensics/config/settings.py` | 53 |
| `ReportConfig` | Class | `src/forensics/config/settings.py` | 249 |
| `EmbeddingRecord` | Class | `src/forensics/models/features.py` | 214 |
| `VerificationResult` | Class | `src/forensics/preregistration.py` | 33 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Generate → Config_fingerprint` | cross_community | 8 |
| `Survey → Parse_datetime` | cross_community | 7 |
| `Survey → Article` | cross_community | 7 |
| `Report → _connect` | cross_community | 7 |
| `Calibrate → Parse_datetime` | cross_community | 7 |
| `Calibrate → Article` | cross_community | 7 |
| `Lock_preregistration_cmd → Config_fingerprint` | cross_community | 7 |
| `Export_data → _project_root` | cross_community | 7 |
| `Run_all → Config_fingerprint` | cross_community | 7 |
| `On_button_pressed → Config_fingerprint` | cross_community | 7 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Unit | 24 calls |
| Features | 11 calls |
| Forensics | 11 calls |
| Storage | 10 calls |
| Scraper | 9 calls |
| Cli | 7 calls |
| Reporting | 6 calls |
| Calibration | 6 calls |

## How to Explore

1. `gitnexus_context({name: "test_insert_analysis_run_persists_row"})` — see callers and callees
2. `gitnexus_query({query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
