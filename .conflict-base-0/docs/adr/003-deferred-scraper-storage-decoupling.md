# ADR-003: Defer scraper / storage decoupling (P2-ARCH-3)

- **Status:** Deferred
- **Date:** 2026-04-21
- **Deciders:** John Eakin

## Context

The Code Review Report (P2-ARCH-3) recommends that crawler/scraper stages return in-memory structures and let an orchestration layer persist to SQLite, instead of importing `Repository` directly from `crawler.py` / `fetcher.py`.

## Decision

**Defer.** The current layout matches the implemented Phase 2–3 pipeline, keeps call sites simple, and avoids a cross-cutting refactor while Phases 4–7 are still stubs. Revisit when adding extract/analyze orchestration or if multiple storage backends are required.

## Consequences

- Scraper modules remain coupled to `forensics.storage.repository` until explicitly replanned.
- Transaction boundaries are improved at the repository layer (see ADR-001) without changing stage boundaries.

## Related

- Code Review Report: P2-ARCH-3
- ADR-002 (CLI dispatch registry): optional follow-up; current handler split is sufficient for now.
