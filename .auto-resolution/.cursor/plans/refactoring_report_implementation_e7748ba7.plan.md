---
name: Refactoring report implementation
overview: Implement all Critical, High, and Medium items from the [Apr 20, 2026 refactoring analysis](https://www.notion.so/abstractdata/Apr-20-2026-mediaite-ghostink-Refactoring-Analysis-Report-3497d7f5629881a5a34ccea46119494e) for mediaite-ghostink, explicitly skipping the Low Issues section (RF-DEAD-001/002, RF-SMELL-003) and related roadmap items that only address those lows.
todos:
  - id: utils-datetime
    content: Consolidate _parse_dt + parse_wp_datetime into forensics/utils; update repository + crawler
    status: completed
  - id: utils-timestamps
    content: Replace inline timestamps and _iso_timestamp with utc_now_iso in crawler + fetcher
    status: completed
  - id: scraper-http-factory
    content: Add create_scraping_client(scraping); replace 3 AsyncClient sites; unify timeout constant
    status: completed
  - id: repo-named-types
    content: Add UnfetchedArticle (+ type for get_unfetched_urls); update repository signatures + fetcher consumers + tests
    status: completed
  - id: scrape-error-helper
    content: Add scrape_error_record; dedupe 8 append_scrape_error call sites in crawler + fetcher
    status: completed
  - id: decompose-fetch-one
    content: Split fetch_articles inner one() into smaller async helpers in fetcher.py
    status: completed
  - id: cli-dispatcher
    content: Refactor _async_scrape to handler functions + dispatcher in cli.py; verify C901 on entrypoint
    status: completed
  - id: repository-class
    content: Introduce Repository(db_path) with instance methods; migrate all imports/callers; keep init_db ergonomic
    status: completed
  - id: verify-tests-ruff
    content: Run uv run pytest and optional ruff C901 on refactored modules
    status: completed
isProject: false
---

# Refactoring report implementation (exclude Low Issues)

**Source:** [Apr 20, 2026: mediaite-ghostink Refactoring Analysis Report](https://www.notion.so/abstractdata/Apr-20-2026-mediaite-ghostink-Refactoring-Analysis-Report-3497d7f5629881a5a34ccea46119494e) (fetched via Notion MCP).

**Out of scope (Low Issues only):**

- **RF-DEAD-001:** Do not add a standalone “remove unused `utc_now_iso`” task; adopting it everywhere (RF-DRY-002) naturally addresses the finding.
- **RF-DEAD-002:** Do not remove or collapse Phase 4–7 stub modules; leave `pass` stubs and smoke-test behavior unchanged.
- **RF-SMELL-003:** Do **not** rename `d`/`m`/`f`/… to `do_discover`/… (explicitly listed as Low). Skip **Quick Win 3** and roadmap **Phase 1 #4** rename-only work.

**Optional / defer:** Roadmap Phase 3 “connection pooling” and “evaluate stub removal” — note only; not required to close the report’s Critical–Medium items.

---

## 1. Medium — shared datetime parsing (RF-ARCH-001)

- Add a single public helper (e.g. `parse_datetime` / `parse_wp_datetime` re-export) in [`src/forensics/utils/`](src/forensics/utils/) — the report suggests `forensics/utils/datetime.py` or extend existing utils; keep one implementation that covers both edge cases today split between [`src/forensics/storage/repository.py`](src/forensics/storage/repository.py) (`_parse_dt`, ~L213–219) and [`src/forensics/scraper/crawler.py`](src/forensics/scraper/crawler.py) (`parse_wp_datetime`, ~L42–47).
- Replace call sites so repository and crawler both import the shared function; delete the duplicate private/parser copies once tests pass.

## 2. Medium — timestamps (RF-DRY-002)

- Remove [`fetcher.py`](src/forensics/scraper/fetcher.py) local `_iso_timestamp()` (~L35–36) and replace all `datetime.now(UTC).isoformat()` in crawler/fetcher with [`utc_now_iso()`](src/forensics/utils/__init__.py) (already exists at ~L9–11).
- Ensure imports stay consistent with the package’s public surface (`forensics.utils.utc_now_iso`).

## 3. Medium — HTTP client factory (RF-DRY-003)

- Introduce one factory in the scraper package (e.g. [`src/forensics/scraper/client.py`](src/forensics/scraper/client.py) or `http.py`): `create_scraping_client(scraping: ScrapingConfig) -> httpx.AsyncClient` using shared headers (`_client_headers` or equivalent), **`DEFAULT_TIMEOUT` from crawler** (eliminate magic `30.0` in fetcher ~L260–265), and `follow_redirects=True`.
- Replace the three `httpx.AsyncClient(...)` construction sites in [`crawler.py`](src/forensics/scraper/crawler.py) (~L176–180, ~L297–301) and [`fetcher.py`](src/forensics/scraper/fetcher.py) (~L260–265).

## 4. Medium — named return types (RF-SMELL-002)

- In [`repository.py`](src/forensics/storage/repository.py) (or [`src/forensics/models/`](src/forensics/models/) if you prefer types next to domain models), define small `NamedTuple` or `@dataclass` types, e.g. `UnfetchedArticle` for `list_unfetched_for_fetch`, and a named type for `get_unfetched_urls`’s `tuple[str, str]`.
- Update [`fetcher.py`](src/forensics/scraper/fetcher.py) consumer (~L380 / positional unpacking) to use attribute access; adjust any tests that assert on raw tuples.

## 5. High — error record builder (RF-DRY-001)

- Add `scrape_error_record(url, status_code, error, phase) -> dict[str, Any]` next to [`append_scrape_error`](src/forensics/scraper/fetcher.py) (~L62+) so the `{"timestamp", "url", "status_code", "error", "phase"}` shape is built once.
- Replace eight inline dict constructions in [`crawler.py`](src/forensics/scraper/crawler.py) and [`fetcher.py`](src/forensics/scraper/fetcher.py) (lines cited in the report) with one-liners calling the helper (import from fetcher in crawler as today for `append_scrape_error`).

## 6. High — decompose `fetch_articles` inner `one()` (RF-CPLX-002)

- In [`fetcher.py`](src/forensics/scraper/fetcher.py), split the ~112-line inner `one()` (~L266–378) into focused async helpers on the same module (names aligned with report: HTTP error path, off-domain redirect handling, successful fetch + parse + merge + warnings + DB write).
- Target: shallower nesting (max depth &lt; 3 where practical) and clearer separation of HTTP vs HTML vs persistence.

## 7. Critical — decompose `_async_scrape` (RF-CPLX-001)

- In [`cli.py`](src/forensics/cli.py), replace the long if/elif chain (~L77–194) with a **dispatcher**: map the seven mutually exclusive flag combinations to small async handlers (`_run_archive_only`, `_run_dedup_only`, `_run_fetch_only`, `_run_fetch_and_dedup`, `_run_discover_only`, `_run_metadata_only`, `_run_full_scrape`, etc.) each ~10–25 lines.
- Keep **identical CLI behavior** and messages unless a test explicitly locks wording (prefer preserving user-visible strings).
- After refactor, run `uv run ruff check . --select C901` (per report) to confirm cyclomatic complexity on the dispatcher entrypoint drops below the ~10 target for the main function.

## 8. High — `Repository` class (RF-SMELL-001)

- Refactor [`repository.py`](src/forensics/storage/repository.py): introduce a `Repository` class holding `db_path`, with instance methods mirroring today’s module-level functions (`get_author`, `upsert_author`, `article_url_exists`, `upsert_article`, `get_article_by_id`, `get_articles_by_author`, `get_all_articles`, `get_unfetched_urls`, `list_unfetched_for_fetch`, `rewrite_raw_paths_after_archive`).
- Centralize `with closing(_connect(self.db_path)) as conn:` / `row_factory` in one or two private helpers on the class to avoid repeating the 10× pattern.
- Keep **`init_db`** as a module-level function **or** a `@staticmethod` on `Repository` — either is fine if [`conftest.py`](tests/conftest.py) and callers stay simple.
- Update all importers: [`fetcher.py`](src/forensics/scraper/fetcher.py), [`crawler.py`](src/forensics/scraper/crawler.py), [`dedup.py`](src/forensics/scraper/dedup.py), [`export.py`](src/forensics/storage/export.py), [`storage/__init__.py`](src/forensics/storage/__init__.py), [`tests/test_storage.py`](tests/test_storage.py), [`tests/test_scraper.py`](tests/test_scraper.py), [`tests/conftest.py`](tests/conftest.py) — pattern: `repo = Repository(db_path)` then `repo.upsert_article(...)`.

```mermaid
flowchart LR
  subgraph foundation [Foundation first]
    dt[parse_datetime util]
    ts[utc_now_iso everywhere]
    http[create_scraping_client]
    err[scrape_error_record]
    nt[UnfetchedArticle types]
  end
  subgraph structural [Structural]
    one[Split fetcher one()]
    cli[CLI scrape dispatcher]
  end
  subgraph arch [Architectural]
    rep[Repository class]
  end
  foundation --> one
  nt --> one
  foundation --> cli
  rep --> one
  rep --> cli
```

## 9. Verification

- `uv run pytest` (full suite).
- Optional: `uv run ruff check . --select C901` on touched paths; optional `radon`/`vulture` only if you want parity with the report’s tooling section.

---

## Risk note (class-based repository)

Introducing [`Repository`](src/forensics/storage/repository.py) touches many call sites but stays **incremental**: same SQL, same behavior, different object boundary — aligned with the approved Notion scope and your request to implement the report (not a provider swap). If you want an even smaller first PR, split PR1 = items 1–6 + 7, PR2 = item 8.
