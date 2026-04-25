---
name: storage
description: "Skill for the Storage area of mediaite-ghostink. 28 symbols across 9 files."
---

# Storage

28 symbols | 9 files | Cohesion: 73%

## When to Use

- Working with code in `src/`
- Understanding how test_write_features_empty_list_writes_zero_rows, test_write_features_roundtrip, test_feature_vector_parquet_dict_field_roundtrip work
- Modifying storage-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/storage/parquet.py` | _serialize_record, write_features, scan_features, read_features, SchemaMigrationRequired (+4) |
| `src/forensics/storage/repository.py` | clear_duplicate_flags, mark_duplicates, _bulk_set_is_duplicate, _connect, open_repository_connection (+2) |
| `tests/test_features.py` | test_write_features_empty_list_writes_zero_rows, test_write_features_roundtrip, test_feature_vector_parquet_dict_field_roundtrip |
| `src/forensics/models/features.py` | FeatureVector, to_flat_dict |
| `src/forensics/storage/migrations/002_feature_parquet_section.py` | _has_target_version, migrate_feature_parquet |
| `src/forensics/scraper/dedup.py` | _duplicate_ids_from_components, deduplicate_articles |
| `tests/test_parquet_embeddings_duckdb.py` | test_load_feature_frame_sorted_requires_timestamp |
| `src/forensics/cli/scrape.py` | _dedup_work |
| `src/forensics/utils/provenance.py` | audit_scrape_timestamps |

## Entry Points

Start here when exploring this area:

- **`test_write_features_empty_list_writes_zero_rows`** (Function) — `tests/test_features.py:441`
- **`test_write_features_roundtrip`** (Function) — `tests/test_features.py:501`
- **`test_feature_vector_parquet_dict_field_roundtrip`** (Function) — `tests/test_features.py:521`
- **`write_features`** (Function) — `src/forensics/storage/parquet.py:145`
- **`scan_features`** (Function) — `src/forensics/storage/parquet.py:156`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `FeatureVector` | Class | `src/forensics/models/features.py` | 161 |
| `SchemaMigrationRequired` | Class | `src/forensics/storage/parquet.py` | 32 |
| `test_write_features_empty_list_writes_zero_rows` | Function | `tests/test_features.py` | 441 |
| `test_write_features_roundtrip` | Function | `tests/test_features.py` | 501 |
| `test_feature_vector_parquet_dict_field_roundtrip` | Function | `tests/test_features.py` | 521 |
| `write_features` | Function | `src/forensics/storage/parquet.py` | 145 |
| `scan_features` | Function | `src/forensics/storage/parquet.py` | 156 |
| `read_features` | Function | `src/forensics/storage/parquet.py` | 165 |
| `to_flat_dict` | Function | `src/forensics/models/features.py` | 198 |
| `test_load_feature_frame_sorted_requires_timestamp` | Function | `tests/test_parquet_embeddings_duckdb.py` | 114 |
| `load_feature_frame_sorted` | Function | `src/forensics/storage/parquet.py` | 184 |
| `load_feature_frame_sorted_eager` | Function | `src/forensics/storage/parquet.py` | 211 |
| `migrate_feature_parquet` | Function | `src/forensics/storage/migrations/002_feature_parquet_section.py` | 33 |
| `deduplicate_articles` | Function | `src/forensics/scraper/dedup.py` | 135 |
| `clear_duplicate_flags` | Function | `src/forensics/storage/repository.py` | 503 |
| `mark_duplicates` | Function | `src/forensics/storage/repository.py` | 510 |
| `audit_scrape_timestamps` | Function | `src/forensics/utils/provenance.py` | 183 |
| `open_repository_connection` | Function | `src/forensics/storage/repository.py` | 126 |
| `_serialize_record` | Function | `src/forensics/storage/parquet.py` | 94 |
| `_read_parquet_schema_version` | Function | `src/forensics/storage/parquet.py` | 52 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Report → _connect` | cross_community | 7 |
| `Run_compare_only → _read_parquet_schema_version` | cross_community | 6 |
| `Run_compare_only → SchemaMigrationRequired` | cross_community | 6 |
| `Analyze → _connect` | cross_community | 6 |
| `Features_migrate → _read_parquet_schema_version` | cross_community | 5 |
| `Run_full_analysis → ForensicsSettings` | cross_community | 5 |
| `Compare_target_to_controls → Scan_features` | cross_community | 5 |
| `Compare_target_to_controls → _read_parquet_schema_version` | cross_community | 5 |
| `Compare_target_to_controls → SchemaMigrationRequired` | cross_community | 5 |
| `Deduplicate_articles → _gram_digest` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 5 calls |
| Scraper | 3 calls |
| Migrations | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_write_features_empty_list_writes_zero_rows"})` — see callers and callees
2. `gitnexus_query({query: "storage"})` — find related execution flows
3. Read key files listed above for implementation details
