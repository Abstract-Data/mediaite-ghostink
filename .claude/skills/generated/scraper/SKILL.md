---
name: scraper
description: "Skill for the Scraper area of mediaite-ghostink. 66 symbols across 15 files."
---

# Scraper

66 symbols | 15 files | Cohesion: 73%

## When to Use

- Working with code in `src/`
- Understanding how test_stable_author_id_deterministic, test_int_header_parsing, test_retry_on_5xx_then_success work
- Modifying scraper-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/scraper/fetcher.py` | wait, scrape_error_record, log_scrape_error, _retry_after_seconds, _exponential_backoff_seconds (+13) |
| `tests/test_scraper.py` | test_stable_author_id_deterministic, test_int_header_parsing, test_retry_on_5xx_then_success, test_write_raw_html_file_rejects_unsafe_article_id, test_write_raw_html_file_accepts_uuid_id (+4) |
| `src/forensics/scraper/crawler.py` | _stable_author_id, _int_header, _fetch_wp_user_rows, _manifests_from_user_rows, _count_posts_for_user (+4) |
| `src/forensics/scraper/parser.py` | extract_article_text, looks_coauthored, _meta_content, _ld_json_blobs, _apply_open_graph_meta (+4) |
| `src/forensics/scraper/dedup.py` | _find, _union, _band_candidate_pairs, _dedup_union_find, _partition_roots |
| `src/forensics/storage/export.py` | _jsonl_append_lock_for_current_loop, append_jsonl, append_jsonl_async |
| `src/forensics/utils/text.py` | word_count, normalize_whitespace, clean_text |
| `src/forensics/storage/json_io.py` | ensure_parent, write_text_atomic |
| `tests/test_dedup_streaming_export.py` | _reference_dup_ids_from_parent, _reference_duplicate_ids_from_pool |
| `src/forensics/utils/__init__.py` | utc_now_iso |

## Entry Points

Start here when exploring this area:

- **`test_stable_author_id_deterministic`** (Function) — `tests/test_scraper.py:42`
- **`test_int_header_parsing`** (Function) — `tests/test_scraper.py:116`
- **`test_retry_on_5xx_then_success`** (Function) — `tests/test_scraper.py:147`
- **`utc_now_iso`** (Function) — `src/forensics/utils/__init__.py:14`
- **`wait`** (Function) — `src/forensics/scraper/fetcher.py:59`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ParsedArticleFetch` | Class | `src/forensics/scraper/fetcher.py` | 281 |
| `FetchConfig` | Class | `src/forensics/scraper/fetcher.py` | 367 |
| `FetchSession` | Class | `src/forensics/scraper/fetcher.py` | 379 |
| `FetchProgressThrottle` | Class | `src/forensics/progress/observer.py` | 92 |
| `test_stable_author_id_deterministic` | Function | `tests/test_scraper.py` | 42 |
| `test_int_header_parsing` | Function | `tests/test_scraper.py` | 116 |
| `test_retry_on_5xx_then_success` | Function | `tests/test_scraper.py` | 147 |
| `utc_now_iso` | Function | `src/forensics/utils/__init__.py` | 14 |
| `wait` | Function | `src/forensics/scraper/fetcher.py` | 59 |
| `scrape_error_record` | Function | `src/forensics/scraper/fetcher.py` | 83 |
| `log_scrape_error` | Function | `src/forensics/scraper/fetcher.py` | 99 |
| `request_with_retry` | Function | `src/forensics/scraper/fetcher.py` | 183 |
| `test_write_raw_html_file_rejects_unsafe_article_id` | Function | `tests/test_scraper.py` | 253 |
| `test_write_raw_html_file_accepts_uuid_id` | Function | `tests/test_scraper.py` | 263 |
| `test_append_jsonl_async_writes_line` | Function | `tests/test_fetcher_phase_a.py` | 28 |
| `append_scrape_error` | Function | `src/forensics/scraper/fetcher.py` | 70 |
| `ensure_parent` | Function | `src/forensics/storage/json_io.py` | 22 |
| `write_text_atomic` | Function | `src/forensics/storage/json_io.py` | 90 |
| `append_jsonl` | Function | `src/forensics/storage/export.py` | 27 |
| `append_jsonl_async` | Function | `src/forensics/storage/export.py` | 33 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_ai_baseline_command → Ensure_parent` | cross_community | 5 |
| `_work → _require_conn` | cross_community | 5 |
| `Request_with_retry → Ensure_parent` | cross_community | 5 |
| `Request_with_retry → _error_lock_for_current_loop` | cross_community | 5 |
| `Request_with_retry → Utc_now_iso` | intra_community | 5 |
| `Lock_preregistration_cmd → Ensure_parent` | cross_community | 4 |
| `Run_full_analysis → Ensure_parent` | cross_community | 4 |
| `Deduplicate_articles → _find` | cross_community | 4 |
| `_work → RateLimiter` | cross_community | 4 |
| `_work → FetchProgressThrottle` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 10 calls |
| Unit | 8 calls |

## How to Explore

1. `gitnexus_context({name: "test_stable_author_id_deterministic"})` — see callers and callees
2. `gitnexus_query({query: "scraper"})` — find related execution flows
3. Read key files listed above for implementation details
