---
name: scraper
description: "Skill for the Scraper area of mediaite-ghostink. 53 symbols across 14 files."
---

# Scraper

53 symbols | 14 files | Cohesion: 70%

## When to Use

- Working with code in `src/`
- Understanding how test_stable_author_id_deterministic, test_int_header_parsing, utc_now_iso work
- Modifying scraper-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/scraper/fetcher.py` | scrape_error_record, log_scrape_error, _retry_after_seconds, _exponential_backoff_seconds, _sleep_exponential_backoff (+8) |
| `src/forensics/scraper/crawler.py` | _stable_author_id, _int_header, _fetch_wp_user_rows, _count_posts_for_user, _ingest_one (+5) |
| `src/forensics/scraper/parser.py` | extract_article_text, looks_coauthored, _meta_content, _ld_json_blobs, _apply_open_graph_meta (+4) |
| `tests/test_scraper.py` | test_stable_author_id_deterministic, test_int_header_parsing, test_extract_article_text_fixture, test_content_validation_short_article_word_count, test_looks_coauthored (+1) |
| `src/forensics/scraper/dedup.py` | _union, _band_candidate_pairs, _dedup_union_find, _partition_roots |
| `src/forensics/utils/text.py` | word_count, normalize_whitespace, clean_text |
| `src/forensics/utils/__init__.py` | utc_now_iso |
| `tests/integration/test_scrape_mock_http.py` | test_discover_authors_writes_manifest_with_mock_http |
| `src/forensics/storage/json_io.py` | write_text_atomic |
| `src/forensics/features/probability_pipeline.py` | _write_model_card |

## Entry Points

Start here when exploring this area:

- **`test_stable_author_id_deterministic`** (Function) — `tests/test_scraper.py:42`
- **`test_int_header_parsing`** (Function) — `tests/test_scraper.py:116`
- **`utc_now_iso`** (Function) — `src/forensics/utils/__init__.py:14`
- **`scrape_error_record`** (Function) — `src/forensics/scraper/fetcher.py:83`
- **`log_scrape_error`** (Function) — `src/forensics/scraper/fetcher.py:99`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ParsedArticleFetch` | Class | `src/forensics/scraper/fetcher.py` | 281 |
| `FetchConfig` | Class | `src/forensics/scraper/fetcher.py` | 367 |
| `FetchSession` | Class | `src/forensics/scraper/fetcher.py` | 379 |
| `FetchProgressThrottle` | Class | `src/forensics/progress/observer.py` | 92 |
| `test_stable_author_id_deterministic` | Function | `tests/test_scraper.py` | 42 |
| `test_int_header_parsing` | Function | `tests/test_scraper.py` | 116 |
| `utc_now_iso` | Function | `src/forensics/utils/__init__.py` | 14 |
| `scrape_error_record` | Function | `src/forensics/scraper/fetcher.py` | 83 |
| `log_scrape_error` | Function | `src/forensics/scraper/fetcher.py` | 99 |
| `request_with_retry` | Function | `src/forensics/scraper/fetcher.py` | 183 |
| `test_extract_article_text_fixture` | Function | `tests/test_scraper.py` | 195 |
| `test_content_validation_short_article_word_count` | Function | `tests/test_scraper.py` | 204 |
| `test_looks_coauthored` | Function | `tests/test_scraper.py` | 219 |
| `word_count` | Function | `src/forensics/utils/text.py` | 20 |
| `extract_article_text` | Function | `src/forensics/scraper/parser.py` | 37 |
| `looks_coauthored` | Function | `src/forensics/scraper/parser.py` | 160 |
| `test_discover_authors_writes_manifest_with_mock_http` | Function | `tests/integration/test_scrape_mock_http.py` | 15 |
| `write_text_atomic` | Function | `src/forensics/storage/json_io.py` | 90 |
| `discover_authors` | Function | `src/forensics/scraper/crawler.py` | 323 |
| `test_extract_metadata_fixture` | Function | `tests/test_scraper.py` | 211 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Discover_authors → Config_fingerprint` | cross_community | 5 |
| `_work → _require_conn` | cross_community | 5 |
| `Request_with_retry → Ensure_parent` | cross_community | 5 |
| `Request_with_retry → _error_lock_for_current_loop` | cross_community | 5 |
| `Request_with_retry → Utc_now_iso` | intra_community | 5 |
| `Lock_preregistration_cmd → Ensure_parent` | cross_community | 4 |
| `Deduplicate_articles → _find` | cross_community | 4 |
| `_work → Client_headers` | cross_community | 4 |
| `_work → RateLimiter` | cross_community | 4 |
| `_work → FetchProgressThrottle` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 17 calls |
| Unit | 4 calls |
| Storage | 2 calls |

## How to Explore

1. `gitnexus_context({name: "test_stable_author_id_deterministic"})` — see callers and callees
2. `gitnexus_query({query: "scraper"})` — find related execution flows
3. Read key files listed above for implementation details
