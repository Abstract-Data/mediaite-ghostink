---
name: tests
description: "Skill for the Tests area of mediaite-ghostink. 487 symbols across 93 files."
---

# Tests

487 symbols | 93 files | Cohesion: 74%

## When to Use

- Working with code in `tests/`
- Understanding how test_init_db_creates_tables, test_upsert_author_round_trip, test_upsert_article_and_query work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/storage/repository.py` | UnfetchedUrl, _author_row_to_model, _validate_batch_size, _row_to_article, RepositoryReader (+23) |
| `tests/test_probability.py` | test_extract_probability_features_writes_parquet_and_model_card, _FakeTensor, size, clone, _FakeTokenizer (+22) |
| `tests/test_scraper.py` | test_parse_wp_datetime_naive_becomes_utc, test_parse_wp_datetime_z_suffix, test_wp_post_to_article, test_article_url_exists_and_duplicate_skip, test_list_unfetched_resumability (+16) |
| `tests/test_report.py` | test_notebook_imports, test_quarto_config_exists, test_index_qmd_exists, _minimal_forensics_settings, _write_result_json (+16) |
| `tests/test_parquet_embeddings_duckdb.py` | test_get_rolling_and_monthly_stats_with_sqlite_and_parquet, test_load_article_embeddings_legacy_npy_and_batch_npz, test_load_article_embeddings_rejects_legacy_object_npz_batch, test_load_article_embeddings_skips_batch_missing_required_keys, test_load_article_embeddings_skips_batch_vector_row_mismatch (+12) |
| `tests/test_calibration.py` | _seed_db_with_author, _make_author, _make_article, _make_ai_article, _make_analysis (+10) |
| `tests/test_survey.py` | _make_author, _make_article, _seed, test_qualification_filters_by_volume, test_qualification_filters_by_date_range (+9) |
| `tests/test_fetcher_phase_a.py` | test_parallel_fetches_complete_all_tasks, _article_html_ctx, test_fetch_http_error_persists_placeholder, test_fetch_off_domain_persists_redirect_marker, test_fetch_resume_skip_when_already_fetched (+8) |
| `tests/test_analysis.py` | test_extract_lda_topic_keywords_runs, test_bocpd_gradual_shift, _detect_bocpd_scalar_reference, test_bocpd_vectorized_matches_reference, test_bocpd_long_signal_runs_quickly (+8) |
| `src/forensics/preflight.py` | PreflightCheck, check_python_version, check_spacy_model, check_sentence_transformer, check_quarto (+8) |

## Entry Points

Start here when exploring this area:

- **`test_init_db_creates_tables`** (Function) — `tests/test_storage.py:30`
- **`test_upsert_author_round_trip`** (Function) — `tests/test_storage.py:46`
- **`test_upsert_article_and_query`** (Function) — `tests/test_storage.py:54`
- **`test_export_articles_jsonl_round_trip`** (Function) — `tests/test_storage.py:65`
- **`test_get_all_articles`** (Function) — `tests/test_storage.py:81`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `UnfetchedUrl` | Class | `src/forensics/storage/repository.py` | 32 |
| `RepositoryReader` | Class | `src/forensics/storage/repository.py` | 199 |
| `Repository` | Class | `src/forensics/storage/repository.py` | 357 |
| `EmbeddingRecord` | Class | `src/forensics/models/features.py` | 214 |
| `Author` | Class | `src/forensics/models/author.py` | 21 |
| `Article` | Class | `src/forensics/models/article.py` | 12 |
| `PreflightCheck` | Class | `src/forensics/preflight.py` | 37 |
| `AnalysisConfig` | Class | `src/forensics/config/settings.py` | 86 |
| `FeaturesConfig` | Class | `src/forensics/config/settings.py` | 204 |
| `QualificationCriteria` | Class | `src/forensics/survey/qualification.py` | 18 |
| `QualifiedAuthor` | Class | `src/forensics/survey/qualification.py` | 45 |
| `RecordingObserver` | Class | `tests/test_pipeline_progress.py` | 15 |
| `AuthorManifest` | Class | `src/forensics/models/author.py` | 11 |
| `ForensicsSettings` | Class | `src/forensics/config/settings.py` | 273 |
| `AuthorDiscoveryResult` | Class | `src/forensics/tui/screens/discovery.py` | 22 |
| `PreflightReport` | Class | `src/forensics/preflight.py` | 46 |
| `UnfetchedArticle` | Class | `src/forensics/storage/repository.py` | 39 |
| `ScrapingConfig` | Class | `src/forensics/config/settings.py` | 53 |
| `AuthorConfig` | Class | `src/forensics/config/settings.py` | 43 |
| `ReportConfig` | Class | `src/forensics/config/settings.py` | 249 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Generate → Config_fingerprint` | cross_community | 8 |
| `Report → _collect_hash_enumerated_fields` | cross_community | 8 |
| `Survey → Parse_datetime` | cross_community | 7 |
| `Survey → Article` | cross_community | 7 |
| `Report → _connect` | cross_community | 7 |
| `Calibrate → Parse_datetime` | cross_community | 7 |
| `Calibrate → Article` | cross_community | 7 |
| `Lock_preregistration_cmd → Config_fingerprint` | cross_community | 7 |
| `Export_data → _project_root` | cross_community | 7 |
| `Run_all → Config_fingerprint` | cross_community | 7 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Unit | 28 calls |
| Scraper | 13 calls |
| Features | 10 calls |
| Analysis | 9 calls |
| Reporting | 8 calls |
| Forensics | 7 calls |
| Storage | 6 calls |
| Calibration | 5 calls |

## How to Explore

1. `gitnexus_context({name: "test_init_db_creates_tables"})` — see callers and callees
2. `gitnexus_query({query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
