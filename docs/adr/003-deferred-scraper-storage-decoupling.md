# ADR-003: Scraper / storage boundary (P2-ARCH-3)

- **Status:** Accepted (partial)
- **Date:** 2026-04-21
- **Deciders:** John Eakin

## Context

The Code Review Report (P2-ARCH-3) recommends that crawler/scraper stages return in-memory structures and let an orchestration layer persist to SQLite, instead of importing `Repository` directly from `crawler.py` / `fetcher.py`.

## Decision

**Hybrid.** Scraper modules still perform persistence (they remain the implementation of the scrape stage), but:

1. **`Repository` is optional at the scrape API boundary** — `collect_article_metadata(..., repo=None)` and `fetch_articles(..., repo=None)` accept an injected `Repository` instance. When omitted, they open their own session (backwards compatible).
2. **CLI orchestration reuses one session** — `forensics.cli.scrape` passes a single `with Repository(db_path) as repo:` into metadata/fetch paths where a full pipeline step should commit atomically (e.g. discover+metadata, full scrape).

Pure in-memory scrape results with a separate persistence stage remain optional future work if a second storage backend is required.

## Consequences

- Reduces connection churn for multi-step scrape flows without rewriting HTML/metadata parsers.
- Scraper modules still import `Repository` for the default path; new code should prefer passing `repo=` from orchestration when batching writes.

## Contract for injected `Repository`

Callers that pass `repo=` into `collect_article_metadata(...)` or `fetch_articles(...)` must respect both halves of the contract:

1. **Session lifetime.** The injected `Repository` must remain open (inside its `with` block) for the full duration of the async call. Closing the repo from another task while the fetch is in flight produces `RuntimeError` from `_require_conn()` — callers, not the scraper, are responsible for that window.
2. **Partial-failure semantics.** When `repo=None` (default), the scraper opens and closes its own session and only the last successful `upsert_*` commit survives on exception. When an external `repo` is injected, rollback on partial failure is the caller's responsibility: callers who require all-or-nothing semantics must wrap the call in an explicit transaction (or re-open a fresh session on retry). The hybrid scraper does not itself emit `BEGIN` / `ROLLBACK`.

These rules are enforceable by inspection — any call site injecting `repo` lives under `forensics.cli.scrape` or `forensics.pipeline`, which today satisfies both.

## Related

- Code Review Report: P2-ARCH-3
- ADR-001 (session-scoped `Repository`)
- ADR-002 (CLI dispatch patterns)
