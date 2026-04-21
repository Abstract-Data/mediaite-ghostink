# Phase 2: Scraper — Author Discovery & Article Metadata — Changelog

## 0.2.0 — 2026-04-20

**Model:** gpt-5-3-codex
**Eval impact:** n/a (prompt-only)

- Expanded implementation spec: pre-flight, scope/non-goals, data paths (`data/articles.db`, manifest, errors), `get_settings()` wiring.
- Documented stable `Author.id` requirement for idempotent `upsert_author`, timezone-aware timestamps, non-interactive manifest refresh (`--force-refresh`), URL idempotency vs schema `UNIQUE`, concurrent error-log note, acceptance checklist, Phase 3 handoff pointer.

## 0.1.0 — 2026-04-20

**Model:** gpt-5-3-codex
**Eval impact:** n/a (initial version)

- Initial spec: WordPress REST API author discovery, article metadata collection, rate limiting, error logging.
