"""HTTP helpers: async rate limiting, HTML fetch, and resilient requests (Phase 2+)."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import tarfile
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from forensics.config.settings import ForensicsSettings, ScrapingConfig, get_project_root
from forensics.models.article import Article
from forensics.scraper.client import create_scraping_client
from forensics.scraper.parser import extract_article_text, extract_metadata, looks_coauthored
from forensics.storage.export import append_jsonl_async
from forensics.storage.repository import Repository, UnfetchedArticle, ensure_repo
from forensics.utils import utc_now_iso
from forensics.utils.hashing import content_hash
from forensics.utils.text import word_count

logger = logging.getLogger(__name__)

# One lock per running event loop (safe across repeated asyncio.run() in tests).
_loop_error_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _error_lock_for_current_loop() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _loop_error_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _loop_error_locks[loop] = lock
    return lock


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

    async with _error_lock_for_current_loop():
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


async def log_scrape_error(
    path: Path,
    url: str,
    status_code: int | None,
    error: str,
    phase: str,
) -> None:
    """Append one structured scrape error (``scrape_error_record`` shape)."""
    await append_scrape_error(path, scrape_error_record(url, status_code, error, phase))


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _exponential_backoff_seconds(attempt: int, backoff_base: float) -> float:
    """Seconds to wait before retry attempt ``attempt`` (0-based) after transport or 5xx errors."""
    return backoff_base * (2**attempt)


async def _sleep_exponential_backoff(attempt: int, backoff_base: float) -> None:
    await asyncio.sleep(_exponential_backoff_seconds(attempt, backoff_base))


async def _handle_retried_response(
    response: httpx.Response,
    *,
    attempt: int,
    max_retries: int,
    backoff_base: float,
    errors_path: Path,
    url: str,
    phase: str,
) -> httpx.Response | None:
    """Return ``response`` when done; return ``None`` to retry the HTTP request."""
    if response.status_code == 404:
        await log_scrape_error(errors_path, url, 404, "Not Found", phase)
        return response

    if response.status_code == 429:
        wait429 = _retry_after_seconds(response) or 30.0
        if attempt >= max_retries:
            await log_scrape_error(
                errors_path,
                url,
                429,
                "Too Many Requests (exhausted retries)",
                phase,
            )
            return response
        logger.warning("429 for %s; sleeping %.1fs", url, wait429)
        await asyncio.sleep(wait429)
        return None

    if 500 <= response.status_code < 600:
        if attempt >= max_retries:
            await log_scrape_error(
                errors_path,
                url,
                response.status_code,
                response.reason_phrase,
                phase,
            )
            return response
        sleep_s = _exponential_backoff_seconds(attempt, backoff_base)
        logger.warning(
            "Server error %s for %s (attempt %s); sleeping %.1fs",
            response.status_code,
            url,
            attempt + 1,
            sleep_s,
        )
        await asyncio.sleep(sleep_s)
        return None

    return response


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
                await log_scrape_error(errors_path, url, None, repr(exc), phase)
                raise
            logger.warning("Request error %s (attempt %s): %s", url, attempt + 1, exc)
            await _sleep_exponential_backoff(attempt, backoff_base)
            attempt += 1
            continue

        finished = await _handle_retried_response(
            response,
            attempt=attempt,
            max_retries=max_retries,
            backoff_base=backoff_base,
            errors_path=errors_path,
            url=url,
            phase=phase,
        )
        if finished is not None:
            return finished
        attempt += 1


def _is_mediaite_host(host: str) -> bool:
    h = host.lower()
    return h == "mediaite.com" or h.endswith(".mediaite.com")


def _write_raw_html_file(root: Path, year: int, article_id: str, html: str) -> str:
    """Write HTML under ``data/raw/{year}/``; returns DB-relative path ``raw/{year}/{id}.html``."""
    if "/" in article_id or "\\" in article_id or ".." in article_id:
        msg = f"unsafe article_id for raw file: {article_id!r}"
        raise ValueError(msg)
    out_dir = root / "data" / "raw" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{article_id}.html"
    path.write_text(html, encoding="utf-8")
    return f"raw/{year}/{article_id}.html"


def _resume_skip_fetch(article: Article | None) -> bool:
    """True when the row is missing or body text is already populated (resume / skip)."""
    if article is None:
        return True
    return bool(article.clean_text.strip())


def _apply_http_failed_mutation(
    article: Article,
    scraped_at: datetime,
    response: httpx.Response,
) -> None:
    article.scraped_at = scraped_at
    article.clean_text = f"[HTTP_ERROR:{response.status_code}]"
    article.word_count = 0
    article.content_hash = content_hash(article.clean_text)


def _apply_off_domain_mutation(
    article: Article,
    scraped_at: datetime,
    final_host: str,
) -> None:
    article.scraped_at = scraped_at
    article.clean_text = f"[REDIRECT:{final_host}]"
    article.word_count = 0
    article.raw_html_path = ""
    article.content_hash = content_hash(article.clean_text)


@dataclass(frozen=True, slots=True)
class ParsedArticleFetch:
    """Pure-compute result of parsing article HTML (no I/O, no mutation)."""

    clean: str
    meta_extra: dict[str, Any]
    wc: int
    author_line: str
    coauth_flag: bool


def _parse_article_html(article: Article, html: str) -> ParsedArticleFetch:
    """Extract text, metadata, word count, and coauthored flag from HTML.

    Split from persistence so persistence can run inside the final db_lock
    critical section (after the resume-skip re-check) without orphaning
    raw files when a concurrent worker wins the race.
    """
    clean = extract_article_text(html)
    meta_extra = extract_metadata(html)
    merged_meta = {**article.metadata, **meta_extra}
    author_line = str(merged_meta.get("page_author") or "")
    coauth_flag = bool(looks_coauthored(author_line) or looks_coauthored(article.title))
    return ParsedArticleFetch(
        clean=clean,
        meta_extra=meta_extra,
        wc=word_count(clean),
        author_line=author_line,
        coauth_flag=coauth_flag,
    )


async def _persist_article_fetch(
    article: Article,
    parsed: ParsedArticleFetch,
    *,
    root: Path,
    year: int,
    article_id: str,
    html: str,
    scraped_at: datetime,
    coauth: Path,
    warns: Path,
) -> None:
    """Write raw HTML, mutate ``article``, and append side-JSONL entries.

    Must run under the DB lock, after the final ``_resume_skip_fetch`` check.
    """
    raw_path = _write_raw_html_file(root, year, article_id, html)
    merged_meta = {**article.metadata, **parsed.meta_extra}
    article.raw_html_path = raw_path
    article.clean_text = parsed.clean
    article.word_count = parsed.wc
    article.content_hash = content_hash(parsed.clean)
    article.scraped_at = scraped_at

    if parsed.coauth_flag:
        merged_meta["coauthored"] = True
        await append_jsonl_async(
            coauth,
            {
                "article_id": article_id,
                "url": str(article.url),
                "title": article.title,
                "author_field": parsed.author_line or article.title,
            },
        )

    article.metadata = merged_meta

    if parsed.wc < 50:
        await append_jsonl_async(
            warns,
            {
                "article_id": article_id,
                "url": str(article.url),
                "word_count": parsed.wc,
                "reason": "below_minimum_word_count",
            },
        )


@dataclass(frozen=True, slots=True)
class ArticleHtmlFetchContext:
    """Paths, locks, and shared counters for one ``fetch_articles`` concurrent HTML run."""

    repo: Repository
    root: Path
    scraping: ScrapingConfig
    limiter: RateLimiter
    errors: Path
    coauth: Path
    warns: Path
    sem: asyncio.Semaphore
    db_lock: asyncio.Lock
    done_lock: asyncio.Lock
    done_count: list[int]
    total: int


async def _persist_and_log(
    ctx: ArticleHtmlFetchContext,
    row: UnfetchedArticle,
    *,
    mutate: Callable[[Article], None] | None,
    log_suffix: str,
    article: Article | None = None,
) -> bool:
    """Persist a fetch result under ``ctx.db_lock`` and log completion under ``ctx.done_lock``.

    Two modes share this ceremony:
    - When ``mutate`` is provided (HTTP-fail, off-domain): read the row, skip if already
      filled, apply ``mutate(row)``, upsert.
    - When ``article`` is provided (success): read the latest row, skip upsert if filled,
      else upsert the caller's pre-built ``article``.

    Returns True when a row was persisted (counter incremented + log emitted),
    False when the write was skipped because the row was already fetched.
    """
    async with ctx.db_lock:
        latest = await asyncio.to_thread(ctx.repo.get_article_by_id, row.article_id)
        if _resume_skip_fetch(latest):
            return False
        if mutate is not None:
            mutate(latest)
            to_write = latest
        else:
            assert article is not None, "provide either `mutate` or `article`"
            to_write = article
        await asyncio.to_thread(ctx.repo.upsert_article, to_write)

    async with ctx.done_lock:
        ctx.done_count[0] += 1
        logger.info(
            "Fetched %s/%s articles for %s%s",
            ctx.done_count[0],
            ctx.total,
            row.author_name,
            log_suffix,
        )
    return True


async def _fetch_one_article_html(
    client: httpx.AsyncClient,
    row: UnfetchedArticle,
    *,
    ctx: ArticleHtmlFetchContext,
) -> None:
    """Fetch one article HTML under concurrency limits; bumps ``ctx.done_count`` on completion."""
    async with ctx.sem:
        year = row.published_date.year
        response = await request_with_retry(
            client,
            ctx.limiter,
            ctx.scraping,
            "GET",
            row.url,
            errors_path=ctx.errors,
            phase="html_fetch",
        )

        scraped_at = datetime.now(UTC)
        final_host = urlparse(str(response.url)).netloc

        if not response.is_success:
            await _persist_and_log(
                ctx,
                row,
                mutate=lambda a: _apply_http_failed_mutation(a, scraped_at, response),
                log_suffix=f" (http {response.status_code})",
            )
            return

        if not _is_mediaite_host(final_host):
            await log_scrape_error(
                ctx.errors,
                str(row.url),
                response.status_code,
                f"redirect_off_domain:{final_host}",
                "html_fetch",
            )
            await _persist_and_log(
                ctx,
                row,
                mutate=lambda a: _apply_off_domain_mutation(a, scraped_at, final_host),
                log_suffix=f" (off-domain {final_host})",
            )
            return

        async with ctx.db_lock:
            article = await asyncio.to_thread(ctx.repo.get_article_by_id, row.article_id)
            if _resume_skip_fetch(article):
                return

        parsed = _parse_article_html(article, response.text)

        async with ctx.db_lock:
            latest = await asyncio.to_thread(ctx.repo.get_article_by_id, row.article_id)
            if _resume_skip_fetch(latest):
                return
            await _persist_article_fetch(
                latest,
                parsed,
                root=ctx.root,
                year=year,
                article_id=row.article_id,
                html=response.text,
                scraped_at=scraped_at,
                coauth=ctx.coauth,
                warns=ctx.warns,
            )
            await asyncio.to_thread(ctx.repo.upsert_article, latest)

        async with ctx.done_lock:
            ctx.done_count[0] += 1
            logger.info(
                "Fetched %s/%s articles for %s",
                ctx.done_count[0],
                ctx.total,
                row.author_name,
            )


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
        with Repository(db_path) as repo:
            repo.rewrite_raw_paths_after_archive(year)
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
    repo: Repository | None = None,
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

    async def _run(r: Repository) -> int:
        rows = r.list_unfetched_for_fetch()
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
        done_count = [0]
        html_ctx = ArticleHtmlFetchContext(
            repo=r,
            root=root,
            scraping=scraping,
            limiter=limiter,
            errors=errors,
            coauth=coauth,
            warns=warns,
            sem=sem,
            db_lock=db_lock,
            done_lock=done_lock,
            done_count=done_count,
            total=total,
        )

        async with create_scraping_client(scraping) as client:
            await asyncio.gather(
                *(_fetch_one_article_html(client, row, ctx=html_ctx) for row in rows)
            )
        return done_count[0]

    with ensure_repo(db_path, repo) as r:
        return await _run(r)
