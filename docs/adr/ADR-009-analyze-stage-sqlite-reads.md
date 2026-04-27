# ADR-009 — Analyze-stage data sources and SQLite `Repository` (C-06 gate)

## Status

**Accepted** — **Option A** (documented exception). Analyze **continues** to open `Repository` / `data/articles.db` for **identity and roster resolution only** (`slug` ↔ `author_id`, configured author rows). Quantitative inputs remain Parquet, embedding batches, and JSON manifests as implemented. Options B/C are **not** pursued unless this ADR is superseded.

**Supersedes:** The earlier “Proposed / approval before Repository removal” gate — removal of SQLite from analyze is **out of scope** under Option A; punch item C-06 is closed as **contract documented**, not **code removed**.

## Date

2026-04-26 (expanded); initial stub same date.

## Context

### Punch list (C-06)

**C-06** flags that the **analysis** package opens SQLite via `Repository` while much of the quantitative work already uses Parquet feature frames, embedding manifests, and JSON analysis outputs.

### Tension with high-level docs

- **AGENTS.md** describes analyze as consuming feature records and writing analysis results; operators often describe this as “analyze reads artifacts.” In practice, **author identity** (`author.id` ↔ `slug`) and roster resolution still come from `articles.db`.
- **ARCHITECTURE.md** states that `forensics extract` reads SQLite and that analyze modules write under `data/analysis/`. It does not currently forbid SQLite reads in analyze; C-06 asks whether they *should* be forbidden for chain-of-custody clarity.

### Why SQLite appears today (summary)

Feature and embedding tensors are Parquet/NPZ-backed, but **stable numeric `author_id`** and **slug → row** mapping live in SQLite. Several analysis paths also reuse helpers that accept a `Repository` for comparison, changepoint entrypoints, drift batch drivers, and sensitivity runs.

## Current inventory (`Repository` in `src/forensics/analysis/`)

| Area | Module(s) | Role of SQLite |
|------|-----------|----------------|
| Per-author pipeline | `orchestrator/per_author.py` | `repo.get_author_by_slug`; joins slug ↔ `author_id` for Parquet filters |
| Serial orchestration | `orchestrator/parallel.py` | Single shared `Repository` when `workers <= 1` |
| Parallel workers | `orchestrator/parallel.py` | Each worker opens **its own** `Repository` (SQLite not fork-safe) |
| Full analysis runner | `orchestrator/runner.py` | Documents worker-owned connections |
| Target vs controls | `comparison.py` | Loads target author + frames; `_load_or_compute_changepoints` takes `Repository` |
| Drift | `drift.py` | `load_article_embeddings`: `get_author_by_slug` to filter manifest by `author_id`; `run_drift_analysis`: `resolve_author_rows` |
| Changepoint CLI path | `changepoint.py` | `run_changepoint_analysis` opens `Repository` |
| Timeseries CLI path | `timeseries.py` | `run_timeseries_analysis` opens `Repository` |
| Sensitivity | `orchestrator/sensitivity.py` | Opens `Repository` for author-scoped work |

Removing `Repository` implies replacing **every** slug/`author_id` dependency with an export that is **as authoritative** as the DB row (including drift detection when manifest rows reference `author_id`).

## Options

### Option A — Documented exception (status quo, explicit contract) ✓ **Accepted**

**Idea:** Keep narrow SQLite reads for roster and `author_id` resolution; document in ARCHITECTURE.md + RUNBOOK that analyze is allowed to open `data/articles.db` via `Repository` for identity joins only; feature math stays on Parquet/embeddings. (Operational **read-only** URI mode is optional future hardening, not required by this ADR.)

| Pros | Cons |
|------|------|
| Lowest engineering and migration risk | Dual read paths; forensic narrative must explain “artifact + index DB” |
| No new extract artifacts required | Does not satisfy a strict “zero SQLite in analyze” reading of C-06 |
| Parallel analyze pattern unchanged at the data-contract layer | |

### Option B — Extract-time export (Parquet/JSON manifest for analyze)

**Idea:** During **extract** (or a dedicated export step), materialize an **analyze bundle**: e.g. `author_index.parquet` / `authors_for_analysis.jsonl` with `{slug, author_id, …}` and optional article id lists versioned beside feature Parquet. Analyze reads **only** files under `data/` that extract produced, plus existing feature/embedding paths.

| Pros | Cons |
|------|------|
| Clean stage story: analyze never opens SQLite | **Touches stage boundary** (extract output contract); requires schema versioning and backfill |
| Easier to reason about reproducibility (hash the bundle) | Must stay in sync when scrape updates DB; stale bundle = wrong joins |
| | Larger implementation + test surface |

### Option C — Read-only SQLite snapshot URI

**Idea:** Analyze opens SQLite only via **`file:…?mode=ro`** (or a copied snapshot file) so the stage never holds a write-capable handle; optionally require an explicit path in config for audits.

| Pros | Cons |
|------|------|
| Addresses write-safety / accidental mutation concerns | Still “SQLite in analyze”; does not satisfy pure artifact-only rhetoric |
| Smaller change than Option B if the goal is custody, not format | Snapshot copy policy (when to refresh) is operational complexity |

## Consequences (shared)

- **Data integrity:** Any option that changes where `author_id` comes from must be regression-tested against drift manifests, comparison reports, and parallel analyze promotion.
- **Preregistration:** If Option B changes inputs to published metrics, treat as analysis-relevant configuration and update lock / amendment per project norms.
- **Parallel analyze:** Today each process opens its own `Repository`; Option B must not reintroduce shared mutable DB state across workers.

## Decision

```
Decision: A — Documented exception (status quo + explicit contract in ARCHITECTURE.md + RUNBOOK.md)
Approved by: Product owner (session directive)
Date: 2026-04-26
Notes: No extract-time author bundle (Option B) and no read-only URI mandate (Option C). Revisit only if air-gapped analyze or strict artifact-only custody becomes a requirement.
```

## Links

- Punch list: `prompts/punch-list/current.md` — **C-06**
- Closure index: `docs/punch-list-closure-index.md` — C-06 → this ADR
- `docs/ARCHITECTURE.md` — stage map and storage layout
- `docs/adr/ADR-002-storage-layer-sqlite-parquet-duckdb.md` — layered storage decision
- `docs/adr/ADR-005-sqlite-connection-management.md` — connection lifecycle
