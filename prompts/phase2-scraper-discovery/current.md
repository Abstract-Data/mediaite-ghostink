# Phase 2: Scraper — Author Discovery & Article Metadata

Version: 0.2.0
Status: draft
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 1 (`src/forensics/models/`, `src/forensics/config/settings.py`, `src/forensics/storage/repository.py`, CLI skeleton)

## Objective

Implement the first step of the two-step scraping approach: use the WordPress REST API to discover all authors at Mediaite, then collect article metadata (URL, title, date) for each configured author. Persist the author manifest to `data/authors_manifest.jsonl` and article metadata to `data/articles.db` via the existing repository. After this phase, `uv run forensics scrape --discover` populates the manifest, and `uv run forensics scrape --metadata` populates article rows for configured authors. HTML bodies remain empty until Phase 3.

## Pre-flight

```bash
cd "$(git rev-parse --show-toplevel)"
uv sync
uv run ruff check .
uv run pytest tests/test_storage.py -v || uv run pytest tests/ -v
```

Confirm Phase 1 models, `get_settings()`, `init_db`, and `upsert_*` behave as documented in `prompts/phase1-scaffold-and-models/current.md` before editing `crawler.py`, `fetcher.py`, or `cli.py`.

## Scope

- WordPress REST only: `wp/v2/users` and `wp/v2/posts` with `_fields` minimization.
- Async HTTP with shared rate limiting, retries, and structured error logging.
- CLI flags on `scrape` for discover / metadata / default combined run.
- Unit tests with mocked HTTP (no live network in CI).

## Non-goals

- Fetching or parsing HTML, paywall bypass, or browser automation (Phase 3).
- Changing storage schema or replacing SQLite (use existing `repository` API).
- Feature extraction, embeddings, or analysis stages.

## Target site

Mediaite (`https://www.mediaite.com`) — WordPress. The REST API returns post metadata; full `content` / `excerpt` are empty for subscriber-gated material. This phase must not depend on body fields.

## Data locations & wiring

| Artifact | Path |
|----------|------|
| SQLite DB | `data/articles.db` (call `init_db(Path("data/articles.db"))` before writes) |
| Author manifest | `data/authors_manifest.jsonl` (one JSON object per line, `AuthorManifest` schema) |
| Scrape errors | `data/scrape_errors.jsonl` |

Load config with `get_settings()` from `forensics.config.settings`. Use `settings.scraping` for delays, user agent, retries. Use `settings.authors` as the list of authors to pull posts for in metadata collection.

## Stable `Author.id` contract

`Author.id` must be **stable across runs** for the same logical author so `upsert_author` updates the same row. The default `uuid4()` factory on the model is not suitable for repeated scrapes. Pick one approach and use it consistently:

- **Recommended:** `uuid.uuid5(uuid.NAMESPACE_URL, f"forensics:author:{slug}")` (or another fixed namespace string) so the same slug always yields the same id, **or**
- Load existing author from SQLite by `slug` before assigning an id (requires a small `get_author_by_slug` query in `repository.py` if you choose this path).

Document the chosen rule in a one-line module comment next to the factory.

## 1. Author discovery (`src/forensics/scraper/crawler.py`)

### `discover_authors(...)`

Paginate:

```http
GET https://www.mediaite.com/wp-json/wp/v2/users?per_page=100&page={n}
```

Use response headers `X-WP-Total` and `X-WP-TotalPages` (fall back to stopping on empty page if headers are missing).

For each user, build `AuthorManifest`:

- `wp_id`: `user["id"]`
- `name`: `user["name"]`
- `slug`: `user["slug"]`
- `total_posts`: from a lightweight posts query (see below)
- `discovered_at`: `datetime.now(timezone.utc)` (avoid naive `utcnow()`)

**Post count per author:**

```http
GET https://www.mediaite.com/wp-json/wp/v2/posts?author={wp_id}&per_page=1&_fields=id
```

Read `X-WP-Total` for the count (0 if absent).

**Manifest file behavior**

- Write all manifests to `data/authors_manifest.jsonl` (JSON Lines).
- If the file already exists: **default** — log and skip discovery unless `--force-refresh` (or equivalent) is passed on the CLI to truncate/overwrite. Do not require interactive stdin (agent/CI safe).

Log summary: total authors, and optionally top N by `total_posts`.

### Implementation notes

- `httpx.AsyncClient` for all requests; timeout from config or sensible default (e.g. 30s).
- Apply `ScrapingConfig.rate_limit_seconds` + `rate_limit_jitter` between requests via the shared limiter in `fetcher.py`.
- Set `User-Agent` to `settings.scraping.user_agent`.
- Per-request errors (4xx/5xx): log, append to `scrape_errors.jsonl`, continue the crawl where reasonable.

## 2. Article metadata collection (`src/forensics/scraper/crawler.py`)

### `collect_article_metadata(db_path: Path, settings: ForensicsSettings)`

For each `AuthorConfig` in `settings.authors`:

1. Resolve `wp_id` by loading `authors_manifest.jsonl` and matching `slug`.
2. If slug missing from manifest: log warning, append error record, `continue`.

Fetch posts with pagination:

```http
GET https://www.mediaite.com/wp-json/wp/v2/posts?author={wp_id}&per_page=100&page={n}&_fields=id,slug,link,title,date
```

Use `X-WP-TotalPages` (or empty-page termination).

For each post, build `Article`:

- `id`: new UUID **or** stable id per URL (if you use URL-based UUID5, document it; otherwise generate `uuid4()` per new row).
- `author_id`: stable `Author.id` for that slug (see contract above).
- `url`: `post["link"]` (must satisfy `HttpUrl`).
- `title`: strip HTML entities from `post["title"]["rendered"]`.
- `published_date`: parse `post["date"]` as ISO 8601 UTC-aware.
- `raw_html_path`: `""`
- `clean_text`: `""` (empty string; schema requires NOT NULL)
- `word_count`: `0`
- `metadata`: `{}` or optional small dict (e.g. `wp_post_id`) if useful.
- `content_hash`: `""`

**Idempotency / duplicates**

- `articles.url` is `UNIQUE` in the schema. Before insert, check for an existing row with the same URL (SQL `SELECT 1 FROM articles WHERE url = ?` or a tiny helper in `repository.py`). If exists, skip insert or update metadata fields only—choose one behavior and test it.
- Re-running metadata must not create duplicate URLs or fatal integrity errors.

**Authors**

- Build `Author` from `AuthorConfig` + manifest `name` (prefer manifest display name if you merge) with stable `id`, then `upsert_author`.

**Logging**

- Per author: `"{n} articles indexed for {name} ({min_date}–{max_date})"` when dates available.

## 3. CLI integration (`src/forensics/cli.py`)

Extend the `scrape` subparser with flags (argparse):

| Invocation | Behavior |
|------------|----------|
| `uv run forensics scrape` | Run discover (if needed or always—document choice; default: discover then metadata) |
| `uv run forensics scrape --discover` | Author discovery + manifest write only |
| `uv run forensics scrape --metadata` | Metadata only; requires readable manifest; init DB if missing |
| `uv run forensics scrape --force-refresh` | With discover: overwrite manifest |

Use `asyncio.run()` to enter async entrypoints. Return non-zero exit code on fatal config errors (e.g. manifest missing when `--metadata` alone).

Replace the placeholder `"Phase not yet implemented"` for the scrape command path once this phase is implemented.

## 4. Rate limiting & resilience (`src/forensics/scraper/fetcher.py`)

Implement shared helpers used by `crawler.py`:

```python
class RateLimiter:
    """Async rate limiter with jitter."""

    def __init__(self, delay: float, jitter: float):
        self.delay = delay
        self.jitter = jitter
        self._last_request = 0.0

    async def wait(self) -> None:
        """Sleep until the next slot is available."""
        ...
```

**Retries** (align with `ScrapingConfig`):

- Up to `max_retries` on 5xx and transport errors.
- Backoff: `retry_backoff_seconds * 2**attempt` with jitter optional.
- `429`: honor `Retry-After` when present, else sleep 30s before retry.
- `404`: no retry; log + error JSONL.
- After exhausting retries, log and record to `scrape_errors.jsonl`.

Optional: thin `async def request_with_retry(client, limiter, method, url, **kwargs)` to avoid duplicating logic in crawler functions.

## 5. Error logging (`data/scrape_errors.jsonl`)

Append one JSON object per line, for example:

```json
{"timestamp": "2026-04-20T12:00:00+00:00", "url": "https://...", "status_code": 404, "error": "Not Found", "phase": "metadata"}
```

Use a module-level lock or serialize writes if multiple tasks log concurrently.

## 6. Tests (`tests/test_scraper.py`)

Use `httpx.MockTransport`, `pytest-httpx`, or respx—**no outbound HTTP in tests**.

Minimum cases:

- Parse sample `wp/v2/users` JSON → list of `AuthorManifest` with expected fields.
- Parse sample `wp/v2/posts` JSON → `Article` instances with correct title/URL/date.
- Pagination: headers `X-WP-Total` / `X-WP-TotalPages` drive the correct number of pages.
- Duplicate URL: second insert skipped or upserted without raising.
- `RateLimiter`: consecutive `wait()` calls respect minimum spacing (use `asyncio` + small fake clock or measure elapsed time with tight tolerances).
- Retries: first response 500, second 200 → succeeds; verify attempt count.

## Acceptance criteria

- [ ] `uv run forensics scrape --discover` creates/refreshes `data/authors_manifest.jsonl` with valid `AuthorManifest` lines.
- [ ] `uv run forensics scrape --metadata` fills `articles` rows for configured slugs; `clean_text` remains empty.
- [ ] Re-running metadata does not duplicate URLs in SQLite.
- [ ] `Author` rows upsert cleanly on repeat runs (stable ids).
- [ ] `uv run pytest tests/test_scraper.py -v` passes without network.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.

## Validation

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_scraper.py -v

# Optional manual smoke (real network; run sparingly):
uv run forensics scrape --discover --force-refresh
wc -l data/authors_manifest.jsonl
uv run forensics scrape --metadata
sqlite3 data/articles.db "SELECT COUNT(*) FROM articles;"
```

## Handoff

`data/authors_manifest.jsonl` lists discovered WordPress authors with post counts. `data/articles.db` holds `authors` and `articles` with metadata and empty `clean_text`, ready for Phase 3 HTML fetch and extraction (`prompts/phase3-scraper-html-fetch/current.md`).
