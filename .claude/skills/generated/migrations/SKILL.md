---
name: migrations
description: "Skill for the Migrations area of mediaite-ghostink. 8 symbols across 4 files."
---

# Migrations

8 symbols | 4 files | Cohesion: 79%

## When to Use

- Working with code in `src/`
- Understanding how apply_migrations, migrate, applied_versions work
- Modifying migrations-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/storage/migrations/__init__.py` | _ensure_schema_version_table, applied_versions, discover_migrations, apply_migrations |
| `src/forensics/storage/migrations/001_author_shared_byline.py` | _column_exists, migrate |
| `src/forensics/storage/repository.py` | apply_migrations |
| `src/forensics/cli/migrate.py` | migrate |

## Entry Points

Start here when exploring this area:

- **`apply_migrations`** (Function) — `src/forensics/storage/repository.py:417`
- **`migrate`** (Function) — `src/forensics/cli/migrate.py:32`
- **`applied_versions`** (Function) — `src/forensics/storage/migrations/__init__.py:55`
- **`discover_migrations`** (Function) — `src/forensics/storage/migrations/__init__.py:62`
- **`apply_migrations`** (Function) — `src/forensics/storage/migrations/__init__.py:84`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `apply_migrations` | Function | `src/forensics/storage/repository.py` | 417 |
| `migrate` | Function | `src/forensics/cli/migrate.py` | 32 |
| `applied_versions` | Function | `src/forensics/storage/migrations/__init__.py` | 55 |
| `discover_migrations` | Function | `src/forensics/storage/migrations/__init__.py` | 62 |
| `apply_migrations` | Function | `src/forensics/storage/migrations/__init__.py` | 84 |
| `migrate` | Function | `src/forensics/storage/migrations/001_author_shared_byline.py` | 20 |
| `_ensure_schema_version_table` | Function | `src/forensics/storage/migrations/__init__.py` | 44 |
| `_column_exists` | Function | `src/forensics/storage/migrations/001_author_shared_byline.py` | 15 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Migrate → Config_fingerprint` | cross_community | 5 |
| `Migrate → _ensure_schema_version_table` | intra_community | 5 |
| `Migrate → Discover_migrations` | intra_community | 4 |
| `__enter__ → _ensure_schema_version_table` | cross_community | 4 |
| `Migrate → _require_conn` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 3 calls |

## How to Explore

1. `gitnexus_context({name: "apply_migrations"})` — see callers and callees
2. `gitnexus_query({query: "migrations"})` — find related execution flows
3. Read key files listed above for implementation details
