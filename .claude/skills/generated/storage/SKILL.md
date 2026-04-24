---
name: storage
description: "Skill for the Storage area of mediaite-ghostink. 32 symbols across 12 files."
---

# Storage

32 symbols | 12 files | Cohesion: 67%

## When to Use

- Working with code in `src/`
- Understanding how test_write_features_empty_list_writes_zero_rows, test_write_features_roundtrip, test_feature_vector_parquet_dict_field_roundtrip work
- Modifying storage-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/storage/parquet.py` | _serialize_record, write_features, scan_features, read_features, SchemaMigrationRequired (+5) |
| `src/forensics/storage/repository.py` | _connect, open_repository_connection, _migrate_articles_columns, __enter__, clear_duplicate_flags (+2) |
| `tests/test_features.py` | test_write_features_empty_list_writes_zero_rows, test_write_features_roundtrip, test_feature_vector_parquet_dict_field_roundtrip |
| `src/forensics/models/features.py` | FeatureVector, to_flat_dict |
| `src/forensics/storage/migrations/002_feature_parquet_section.py` | _has_target_version, migrate_feature_parquet |
| `src/forensics/scraper/fetcher.py` | _error_lock_for_current_loop, append_scrape_error |
| `tests/test_parquet_embeddings_duckdb.py` | test_load_feature_frame_sorted_requires_timestamp |
| `src/forensics/utils/provenance.py` | audit_scrape_timestamps |
| `src/forensics/scraper/dedup.py` | deduplicate_articles |
| `src/forensics/cli/scrape.py` | _dedup_work |

## Entry Points

Start here when exploring this area:

- **`test_write_features_empty_list_writes_zero_rows`** (Function) — `tests/test_features.py:423`
- **`test_write_features_roundtrip`** (Function) — `tests/test_features.py:483`
- **`test_feature_vector_parquet_dict_field_roundtrip`** (Function) — `tests/test_features.py:503`
- **`write_features`** (Function) — `src/forensics/storage/parquet.py:145`
- **`scan_features`** (Function) — `src/forensics/storage/parquet.py:156`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `FeatureVector` | Class | `src/forensics/models/features.py` | 161 |
| `SchemaMigrationRequired` | Class | `src/forensics/storage/parquet.py` | 32 |
| `test_write_features_empty_list_writes_zero_rows` | Function | `tests/test_features.py` | 423 |
| `test_write_features_roundtrip` | Function | `tests/test_features.py` | 483 |
| `test_feature_vector_parquet_dict_field_roundtrip` | Function | `tests/test_features.py` | 503 |
| `write_features` | Function | `src/forensics/storage/parquet.py` | 145 |
| `scan_features` | Function | `src/forensics/storage/parquet.py` | 156 |
| `read_features` | Function | `src/forensics/storage/parquet.py` | 165 |
| `to_flat_dict` | Function | `src/forensics/models/features.py` | 198 |
| `test_load_feature_frame_sorted_requires_timestamp` | Function | `tests/test_parquet_embeddings_duckdb.py` | 114 |
| `load_feature_frame_sorted` | Function | `src/forensics/storage/parquet.py` | 184 |
| `load_feature_frame_sorted_eager` | Function | `src/forensics/storage/parquet.py` | 211 |
| `migrate_feature_parquet` | Function | `src/forensics/storage/migrations/002_feature_parquet_section.py` | 33 |
| `open_repository_connection` | Function | `src/forensics/storage/repository.py` | 126 |
| `audit_scrape_timestamps` | Function | `src/forensics/utils/provenance.py` | 143 |
| `clear_duplicate_flags` | Function | `src/forensics/storage/repository.py` | 503 |
| `mark_duplicates` | Function | `src/forensics/storage/repository.py` | 510 |
| `deduplicate_articles` | Function | `src/forensics/scraper/dedup.py` | 135 |
| `save_numpy_compressed_atomic` | Function | `src/forensics/storage/parquet.py` | 139 |
| `ensure_parent` | Function | `src/forensics/storage/json_io.py` | 22 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Report → _connect` | cross_community | 7 |
| `Analyze → _connect` | cross_community | 6 |
| `Run_compare_only → _read_parquet_schema_version` | cross_community | 6 |
| `Run_compare_only → SchemaMigrationRequired` | cross_community | 6 |
| `Run_compare_only → Scan_features` | cross_community | 6 |
| `Features_migrate → _read_parquet_schema_version` | cross_community | 5 |
| `Run_full_analysis → ForensicsSettings` | cross_community | 5 |
| `Compare_target_to_controls → _read_parquet_schema_version` | cross_community | 5 |
| `Compare_target_to_controls → SchemaMigrationRequired` | cross_community | 5 |
| `Compare_target_to_controls → Scan_features` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 5 calls |
| Migrations | 1 calls |
| Features | 1 calls |
| Scraper | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_write_features_empty_list_writes_zero_rows"})` — see callers and callees
2. `gitnexus_query({query: "storage"})` — find related execution flows
3. Read key files listed above for implementation details
