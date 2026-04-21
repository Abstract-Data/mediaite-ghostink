"""HTTP helpers: async rate limiting, HTML fetch, and resilient requests (Phase 2+)."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from forensics.config.settings import ForensicsSettings, ScrapingConfig, get_project_root
from forensics.models.article import Article
from forensics.scraper.client import create_scraping_client
from forensics.scraper.parser import extract_article_text, extract_metadata, looks_coauthored
from forensics.storage.export import append_jsonl
from forensics.storage.repository import Repository, init_db
from forensics.utils import utc_now_iso
from forensics.utils.hashing import content_hash
from forensics.utils.text import word_count

logger = logging.getLogger(__name__)

_error_lock = asyncio.Lock()


class RateLimiter:
    """Async rate limiter enforcing a minimum gap between successive waits."""

    def __init__(self, delay: float, jitter: float) -> None:
        self.delay = max(0.0, delay)
        self.jitter = max(0.0, jitter)
        self._lock = asyncio.Lock()
        self._last_wait_end = 0.0

    async def wait(self) -> None:
        """Block until at least ``delay + random[0, jitter]`` seconds since the prior wait ended."""
        async with self._lock:
            now = time.monotonic()
            gap = self.delay + (random.uniform(0.0, self.jitter) if self.jitter else 0.0)
            elapsed = now - self._last_wait_end
            if elapsed < gap:
                await asyncio.sleep(gap - elapsed)
            self._last_wait_end = time.monotonic()


async def append_scrape_error(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object to ``path`` (line-delimited), serialized across concurrent callers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str) + "\n"

    def _write() -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    async with _error_lock:
        await asyncio.to_thread(_write)


def scrape_error_record(
    url: str,
    status_code: int | None,
    error: str,
    phase: str,
) -> dict[str, Any]:
    """Structured line for ``append_scrape_error`` (timestamp, url, status, error, phase)."""
    return {
        "timestamp": utc_now_iso(),
        "url": url,
        "status_code": status_code,
        "error": error,
        "phase": phase,
    }


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def request_with_retry(
    client: httpx.AsyncClient,
    limiter: RateLimiter,
    scraping: ScrapingConfig,
    method: str,
    url: str,
    *,
    errors_path: Path,
    phase: str,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP request with rate limiting, retries, and structured error logging."""
    max_retries = max(0, scraping.max_retries)
    backoff_base = max(0.0, scraping.retry_backoff_seconds)
    attempt = 0

    while True:
        await limiter.wait()
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            if attempt >= max_retries:
                await append_scrape_error(
                    errors_path,
                    scrape_error_record(url, None, repr(exc), phase),
                )
                raise
            sleep_s = backoff_base * (2**attempt)
            logger.warning("Request error %s (attempt %s): %s", url, attempt + 1, exc)
            await asyncio.sleep(sleep_s)
            attempt += 1
            continue

        if response.status_code == 404:
            await append_scrape_error(
                errors_path,
                scrape_error_record(url, 404, "Not Found", phase),
            )
            return response

        if response.status_code == 429:
            wait429 = _retry_after_seconds(response) or 30.0
            if attempt >= max_retries:
                await append_scrape_error(
                    errors_path,
                    scrape_error_record(
                        url,
                        429,
                        "Too Many Requests (exhausted retries)",
                        phase,
                    ),
                )
                return response
            logger.warning("429 for %s; sleeping %.1fs", url, wait429)
            await asyncio.sleep(wait429)
            attempt += 1
            continue

        if 500 <= response.status_code < 600:
            if attempt >= max_retries:
                await append_scrape_error(
                    errors_path,
                    scrape_error_record(
                        url,
                        response.status_code,
                        response.reason_phrase,
                        phase,
                    ),
                )
                return response
            sleep_s = backoff_base * (2**attempt)
            logger.warning(
                "Server error %s for %s (attempt %s); sleeping %.1fs",
                response.status_code,
                url,
                attempt + 1,
                sleep_s,
            )
            await asyncio.sleep(sleep_s)
            attempt += 1
            continue

        return response


def _is_mediaite_host(host: str) -> bool:
    h = host.lower()
    return h == "mediaite.com" or h.endswith(".mediaite.com")


def _write_raw_html_file(root: Path, year: int, article_id: str, html: str) -> str:
    """Write HTML under ``data/raw/{year}/``; returns DB-relative path ``raw/{year}/{id}.html``."""
    out_dir = root / "data" / "raw" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{article_id}.html"
    path.write_text(html, encoding="utf-8")
    return f"raw/{year}/{article_id}.html"


async def _persist_http_failed_fetch(
    repo: Repository,
    article: Article,
    scraped_at: datetime,
    response: httpx.Response,
) -> None:
    article.scraped_at = scraped_at
    article.clean_text = f"[HTTP_ERROR:{response.status_code}]"
    article.word_count = 0
    article.content_hash = content_hash(article.clean_text)
    repo.upsert_article(article)


async def _persist_off_domain_fetch(
    repo: Repository,
    errors: Path,
    article: Article,
    scraped_at: datetime,
    url: str,
    response: httpx.Response,
    final_host: str,
) -> None:
    await append_scrape_error(
        errors,
        scrape_error_record(
            url,
            response.status_code,
            f"redirect_off_domain:{final_host}",
            "html_fetch",
        ),
    )
    article.scraped_at = scraped_at
    article.clean_text = f"[REDIRECT:{final_host}]"
    article.word_count = 0
    article.raw_html_path = ""
    article.content_hash = content_hash(article.clean_text)
    repo.upsert_article(article)


async def _persist_successful_fetch(
    repo: Repository,
    root: Path,
    year: int,
    article_id: str,
    article: Article,
    html: str,
    scraped_at: datetime,
    coauth: Path,
    warns: Path,
) -> None:
    raw_path = _write_raw_html_file(root, year, article_id, html)
    clean = extract_article_text(html)
    meta_extra = extract_metadata(html)
    merged_meta = {**article.metadata, **meta_extra}
    article.metadata = merged_meta
    wc = word_count(clean)
    article.raw_html_path = raw_path
    article.clean_text = clean
    article.word_count = wc
    article.content_hash = content_hash(clean)
    article.scraped_at = scraped_at

    author_line = str(merged_meta.get("page_author") or "")
    if looks_coauthored(author_line) or looks_coauthored(article.title):
        append_jsonl(
            coauth,
            {
                "article_id": article_id,
                "url": str(article.url),
                "title": article.title,
                "author_field": author_line or article.title,
            },
        )
        merged_meta["coauthored"] = True
        article.metadata = merged_meta

    if wc < 50:
        append_jsonl(
            warns,
            {
                "article_id": article_id,
                "url": str(article.url),
                "word_count": wc,
                "reason": "below_minimum_word_count",
            },
        )

    repo.upsert_article(article)


def archive_raw_year_dirs(root: Path, db_path: Path) -> int:
    """
    Compress each ``data/raw/{YYYY}/`` directory to ``data/raw/{YYYY}.tar.gz`` and
    rewrite ``raw_html_path`` in SQLite to ``raw/{YYYY}.tar.gz:{id}.html``.
    """
    raw = root / "data" / "raw"
    if not raw.is_dir():
        return 0
    processed = 0
    for child in sorted(raw.iterdir()):
        if not child.is_dir():
            continue
        if not child.name.isdigit() or len(child.name) != 4:
            continue
        year = int(child.name)
        tgz = raw / f"{child.name}.tar.gz"
        with tarfile.open(tgz, "w:gz") as archive:
            for html_file in sorted(child.glob("*.html")):
                archive.add(html_file, arcname=html_file.name)
        Repository(db_path).rewrite_raw_paths_after_archive(year)
        shutil.rmtree(child)
        processed += 1
    return processed


async def fetch_articles(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    dry_run: bool = False,
    errors_path: Path | None = None,
    warnings_path: Path | None = None,
    coauthored_path: Path | None = None,
) -> int:
    """
    Fetch HTML for articles with empty ``clean_text``, extract body, update SQLite.

    Returns the number of articles successfully processed (or that would be fetched when
    ``dry_run`` is True).
    """
    root = get_project_root()
    errors = errors_path or (root / "data/scrape_errors.jsonl")
    warns = warnings_path or (root / "data/extraction_warnings.jsonl")
    coauth = coauthored_path or (root / "data/coauthored_articles.jsonl")

    init_db(db_path)
    repo = Repository(db_path)
    rows = repo.list_unfetched_for_fetch()
    total = len(rows)
    if dry_run:
        logger.info("dry-run: %s article(s) would be fetched", total)
        return total

    if not rows:
        return 0

    scraping = settings.scraping
    limiter = RateLimiter(scraping.rate_limit_seconds, scraping.rate_limit_jitter)
    sem = asyncio.Semaphore(max(1, scraping.max_concurrent))
    db_lock = asyncio.Lock()
    done_lock = asyncio.Lock()
    done_count = 0

    async def one(
        client: httpx.AsyncClient, article_id: str, url: str, author_name: str, published: datetime
    ) -> None:
        nonlocal done_count
        async with sem:
            year = published.year
            response = await request_with_retry(
                client,
                limiter,
                scraping,
                "GET",
                url,
                errors_path=errors,
                phase="html_fetch",
            )

            scraped_at = datetime.now(UTC)
            final_host = urlparse(str(response.url)).netloc

            async with db_lock:
                article = repo.get_article_by_id(article_id)
                if article is None or (article.clean_text and article.clean_text.strip()):
                    return

                if not response.is_success:
                    await _persist_http_failed_fetch(repo, article, scraped_at, response)
                    async with done_lock:
                        done_count += 1
                        logger.info(
                            "Fetched %s/%s articles for %s (http %s)",
                            done_count,
                            total,
                            author_name,
                            response.status_code,
                        )
                    return

                if not _is_mediaite_host(final_host):
                    await _persist_off_domain_fetch(
                        repo,
                        errors,
                        article,
                        scraped_at,
                        url,
                        response,
                        final_host,
                    )
                    async with done_lock:
                        done_count += 1
                        logger.info(
                            "Fetched %s/%s articles for %s (off-domain %s)",
                            done_count,
                            total,
                            author_name,
                            final_host,
                        )
                    return

                await _persist_successful_fetch(
                    repo,
                    root,
                    year,
                    article_id,
                    article,
                    response.text,
                    scraped_at,
                    coauth,
                    warns,
                )

            async with done_lock:
                done_count += 1
                logger.info("Fetched %s/%s articles for %s", done_count, total, author_name)

    async with create_scraping_client(scraping) as client:
        await asyncio.gather(
            *(
                one(client, row.article_id, row.url, row.author_name, row.published_date)
                for row in rows
            )
        )
    return done_count
