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

## Related

- Code Review Report: P2-ARCH-3
- ADR-001 (session-scoped `Repository`)
- ADR-002 (CLI dispatch patterns)
