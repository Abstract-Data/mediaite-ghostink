---
name: migrations
description: "Skill for the Migrations area of mediaite-ghostink. 6 symbols across 2 files."
---

# Migrations

6 symbols | 2 files | Cohesion: 83%

## When to Use

- Working with code in `src/`
- Understanding how applied_versions, discover_migrations, apply_migrations work
- Modifying migrations-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/forensics/storage/migrations/__init__.py` | _ensure_schema_version_table, applied_versions, discover_migrations, apply_migrations |
| `src/forensics/storage/migrations/001_author_shared_byline.py` | _column_exists, migrate |

## Entry Points

Start here when exploring this area:

- **`applied_versions`** (Function) — `src/forensics/storage/migrations/__init__.py:55`
- **`discover_migrations`** (Function) — `src/forensics/storage/migrations/__init__.py:62`
- **`apply_migrations`** (Function) — `src/forensics/storage/migrations/__init__.py:84`
- **`migrate`** (Function) — `src/forensics/storage/migrations/001_author_shared_byline.py:20`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `applied_versions` | Function | `src/forensics/storage/migrations/__init__.py` | 55 |
| `discover_migrations` | Function | `src/forensics/storage/migrations/__init__.py` | 62 |
| `apply_migrations` | Function | `src/forensics/storage/migrations/__init__.py` | 84 |
| `migrate` | Function | `src/forensics/storage/migrations/001_author_shared_byline.py` | 20 |
| `_ensure_schema_version_table` | Function | `src/forensics/storage/migrations/__init__.py` | 44 |
| `_column_exists` | Function | `src/forensics/storage/migrations/001_author_shared_byline.py` | 15 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Migrate → _ensure_schema_version_table` | cross_community | 5 |
| `Migrate → Discover_migrations` | cross_community | 4 |
| `__enter__ → _ensure_schema_version_table` | cross_community | 4 |

## How to Explore

1. `gitnexus_context({name: "applied_versions"})` — see callers and callees
2. `gitnexus_query({query: "migrations"})` — find related execution flows
3. Read key files listed above for implementation details
