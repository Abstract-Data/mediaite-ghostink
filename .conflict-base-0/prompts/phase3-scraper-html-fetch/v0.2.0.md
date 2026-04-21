# Phase 3: Scraper — HTML Fetching, Text Extraction & Deduplication

Version: 0.2.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 2 (author discovery, article metadata in SQLite)

## Objective

Implement the second step of the two-step scraping approach: for every article URL in SQLite that lacks body text, fetch the full HTML page, extract clean article text, run deduplication, and store results. After this phase, `uv run forensics scrape` is fully functional end-to-end and the SQLite database contains clean article text for all configured authors.

## 1. HTML Fetcher (src/forensics/scraper/fetcher.py)

### fetch_articles(db_path: Path, config: ScrapingConfig)

Query SQLite for all articles where `clean_text` is empty (use `repository.get_unfetched_urls()`). For each URL:

1. Fetch the full HTML page using `httpx.AsyncClient`
2. Respect rate limiting: default 2.0s delay with 0.5s jitter between HTML fetches (these are heavier than API calls)
3. Limit concurrency to `max_concurrent` (default 3) using `asyncio.Semaphore`
4. Store raw HTML to compressed archive (see section 3 below)
5. Extract clean text via the parser
6. Compute content hash
7. Record `scraped_at` timestamp (UTC) for chain-of-custody
8. Update the article record in SQLite with `clean_text`, `word_count`, `raw_html_path`, `content_hash`, `scraped_at`

### Resumability

The fetch is inherently resumable: it only processes articles with empty `clean_text`. An interrupted run picks up where it left off on next invocation. Log progress: "Fetched {n}/{total} articles for {author_name}".

### Domain validation

Before extracting text, verify the final URL domain (after redirects) is still `mediaite.com`. Some articles tagged as `crosspost` redirect to external sites like `lawandcrime.com`. If the domain doesn't match:
- Log the redirect to `data/scrape_errors.jsonl`
- Mark the article with `clean_text = "[REDIRECT:{final_domain}]"` so it's skipped in extraction
- Do not retry

## 2. HTML Parser (src/forensics/scraper/parser.py)

### extract_article_text(html: str) -> str

Use `BeautifulSoup` with `lxml` parser. Extraction strategy (in order of preference):

1. `soup.find("div", class_="entry-content")` — standard WordPress content container
2. `soup.find("article")` — fallback to article tag
3. `soup.find("div", class_="post-content")` — alternate WordPress theme class
4. If all fail, return empty string and log for manual review

Within the found container:
- Remove `<script>`, `<style>`, `<nav>`, `<aside>`, `<footer>` tags
- Remove elements with classes like `related-posts`, `social-share`, `advertisement`, `sidebar`
- Extract text with `get_text(separator="\n")`
- Run through `utils.text.clean_text()` for normalization

### extract_metadata(html: str) -> dict

Extract additional metadata from the page:
- `og:section` or category from meta tags
- Tags from `article:tag` meta properties
- Any `schema.org` structured data (author, datePublished confirmation)

Return as a flat dict for storage in the article's `metadata` JSON field.

## 2a. WordPress Editorial Metadata Collection

During Phase 2 API metadata collection (or as an enrichment pass in Phase 3), collect additional WordPress fields for editorial confound control:

### Additional API fields to request

Add `_fields=modified,meta` to the WordPress REST API article queries. For each article, store:

- **`modified_date`** — WordPress `modified` field (ISO 8601). This is when the article was last edited in WordPress, regardless of byline author.
- **`modifier_user_id`** — If available via `meta` or `_embedded.author`, the WordPress user ID of the last modifier. Not all WordPress configs expose this, so handle gracefully if absent.
- **`post_modification_delta`** — Computed field: `modified_date - published_date` in hours. AI-assisted drafts that were lightly edited often show very short deltas; human drafts often show significant revision post-publication.

### Schema additions to SQLite

Add three columns to the `articles` table:
```sql
ALTER TABLE articles ADD COLUMN modified_date TEXT;       -- ISO 8601
ALTER TABLE articles ADD COLUMN modifier_user_id INTEGER; -- nullable
ALTER TABLE articles ADD COLUMN scraped_at TEXT;          -- ISO 8601 UTC, chain of custody
```

The `post_modification_delta` is computed at query time via DuckDB, not stored.

### Chain of custody

Every article record must include a `scraped_at` timestamp recording when the content was fetched. This establishes the "data freeze" moment for forensic defensibility. The scrape timestamp is separate from `published_date` (when the article was originally published) and `modified_date` (when it was last edited in WordPress).

## 3. Raw HTML Storage

Store raw HTML in yearly compressed archives under `data/raw/`:

```
data/raw/2014.tar.gz
data/raw/2015.tar.gz
...
data/raw/2025.tar.gz
```

Each article's HTML is stored as `{article_id}.html` within the archive for its publication year. The `raw_html_path` field in SQLite stores the relative path like `raw/2023.tar.gz:{article_id}.html`.

Implementation note: for simplicity during scraping, write HTML files to `data/raw/{year}/` directories first, then compress to `.tar.gz` as a post-processing step (or on `scrape --archive` flag). Don't block the main fetch loop on compression.

## 4. Deduplication (src/forensics/scraper/dedup.py)

### deduplicate_articles(db_path: Path) -> list[str]

After fetching, run near-duplicate detection using simhash:

1. Load all articles with non-empty `clean_text` from SQLite
2. For each article, compute simhash via `utils.hashing.simhash()`
3. Compare simhash values — articles with Hamming distance <= 3 are near-duplicates
4. For duplicate groups, keep the earliest-published article and mark others
5. Return list of duplicate article IDs
6. Log duplicate pairs: "DUPLICATE: '{title_a}' ({date_a}) ≈ '{title_b}' ({date_b})"

Do NOT delete duplicates from the database. Add a `is_duplicate` flag or store duplicate mappings in a separate table/JSONL file so they can be excluded from analysis without data loss.

### Co-authored article detection

Flag articles where the author field in metadata contains multiple names (e.g., "Aidan McLaughlin and Caleb Howe"). These should be logged and excluded from single-author analysis. Store in `data/coauthored_articles.jsonl`.

## 5. Content Validation

After extraction, validate each article:
- Articles with fewer than 50 words of clean text are flagged as potential extraction failures
- Log these to `data/extraction_warnings.jsonl` with the URL for manual review
- They remain in the database but should be excluded from feature extraction

## 6. CLI Integration

Update the `scrape` command:

```
uv run forensics scrape                # full pipeline: discover + metadata + fetch + dedup
uv run forensics scrape --discover     # Phase 2: author discovery only
uv run forensics scrape --metadata     # Phase 2: article metadata only
uv run forensics scrape --fetch        # Phase 3: HTML fetch + extract only
uv run forensics scrape --dedup        # Phase 3: deduplication pass only
uv run forensics scrape --archive      # compress raw HTML to tar.gz
```

Also add a `--dry-run` flag that reports what would be fetched without making requests.

## 7. JSONL Export

After scraping completes, automatically export all articles to `data/articles.jsonl` using `storage.export.export_articles_jsonl()`. This is the human-readable, diffable companion to the SQLite database. Both get committed to the repo.

## 8. Tests (tests/test_scraper.py)

Add to existing test file:

- **test_extract_article_text**: Given sample Mediaite HTML (create a fixture), verify correct text extraction
- **test_extract_metadata**: Verify og:section and tags are extracted
- **test_redirect_detection**: Given an HTTP response with a redirect to lawandcrime.com, verify it's flagged
- **test_content_validation**: Verify articles under 50 words are flagged
- **test_simhash_dedup**: Create two nearly identical texts and verify they're flagged as duplicates
- **test_simhash_distinct**: Create two genuinely different texts and verify they're NOT flagged
- **test_resumability**: Insert an article with empty clean_text, run fetch mock, verify it gets populated. Insert an article with existing clean_text, verify it's skipped.

Create an HTML fixture file at `tests/fixtures/sample_mediaite_article.html` with a representative Mediaite article structure (fabricated content, real DOM structure).

## Validation

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_scraper.py -v

# Smoke test (requires Phase 2 to have run first):
uv run forensics scrape --fetch --dry-run
# Should report N unfetched URLs

# Full fetch (makes real requests):
uv run forensics scrape --fetch
# Check results:
sqlite3 data/articles.db "SELECT COUNT(*) FROM articles WHERE clean_text != ''"
```

## Handoff

After this phase, the scraping pipeline is complete. SQLite contains full article text for all configured authors. `data/articles.jsonl` is the human-readable export. Duplicates and co-authored articles are flagged. The corpus is ready for Phase 4 (feature extraction).
