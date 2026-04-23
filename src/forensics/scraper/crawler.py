"""Author discovery and WordPress REST metadata collection (Phase 2)."""

from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

import httpx

from forensics.config.settings import (
    AuthorConfig,
    ForensicsSettings,
    ScrapingConfig,
    get_project_root,
)
from forensics.models.article import Article
from forensics.models.author import Author, AuthorManifest
from forensics.scraper.client import create_scraping_client
from forensics.scraper.fetcher import RateLimiter, log_scrape_error, request_with_retry
from forensics.scraper.parser import extract_article_text_from_rest
from forensics.storage.repository import Repository, ensure_repo
from forensics.utils.datetime import parse_wp_datetime
from forensics.utils.hashing import content_hash as compute_content_hash
from forensics.utils.text import word_count

logger = logging.getLogger(__name__)

# Stable entrypoints for CLI and cross-module idempotency; everything else is internal.
__all__ = (
    "collect_article_metadata",
    "discover_authors",
    "posts_year_query_fragment",
    "resolve_posts_year_window",
    "stable_article_id",
)

MEDIAITE_REST = "https://www.mediaite.com/wp-json/wp/v2"


def resolve_posts_year_window(
    scraping: ScrapingConfig,
    *,
    override_min: int | None = None,
    override_max: int | None = None,
) -> tuple[int, int] | None:
    """Return inclusive ``(year_min, year_max)`` for WordPress post queries, or ``None``.

    Config values apply when the corresponding override is omitted. CLI overrides
    take precedence per side. Both min and max must be defined to enable filtering
    (either from config or from overrides — mixing is allowed).
    """
    m = scraping.post_year_min if override_min is None else override_min
    x = scraping.post_year_max if override_max is None else override_max
    if m is None and x is None:
        return None
    if m is None or x is None:
        msg = (
            "posts year filter requires both min and max calendar years "
            "(set scraping.post_year_min and post_year_max in config.toml, "
            "or pass both --post-year-min and --post-year-max)"
        )
        raise ValueError(msg)
    if x < m:
        msg = "post year max must be >= post year min"
        raise ValueError(msg)
    return (m, x)


def posts_year_query_fragment(year_min: int, year_max: int) -> str:
    """URL suffix with WordPress ``after`` / ``before`` (UTC) for inclusive calendar years."""
    after = f"{year_min:04d}-01-01T00:00:00Z"
    before = f"{year_max + 1:04d}-01-01T00:00:00Z"
    return f"&after={quote(after, safe='')}&before={quote(before, safe='')}"


def _stable_author_id(slug: str) -> str:
    """Deterministic UUID5 per slug so upsert_author targets one row across runs."""
    return str(uuid5(NAMESPACE_URL, f"forensics:author:{slug}"))


def stable_article_id(url: str) -> str:
    """Deterministic UUID5 per canonical article URL for idempotent upserts."""
    return str(uuid5(NAMESPACE_URL, f"forensics:article:{url}"))


def _modifier_user_id_from_post(post: dict[str, object]) -> int | None:
    raw_meta = post.get("meta")
    if isinstance(raw_meta, dict):
        for key in ("_edit_last", "last_modified_by", "modifier_user_id"):
            val = raw_meta.get(key)
            if val is None:
                continue
            try:
                if isinstance(val, list) and val:
                    return int(val[0])
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _wp_post_to_article(post: dict[str, object], author_id: str) -> Article:
    """Build an ``Article`` from a ``wp/v2/posts`` element (metadata fields only)."""
    link = str(post["link"])
    title_raw = str(post["title"]["rendered"])  # type: ignore[index]
    title = html.unescape(title_raw)
    published = parse_wp_datetime(str(post["date"]))
    modified_date: datetime | None = None
    if post.get("modified"):
        try:
            modified_date = parse_wp_datetime(str(post["modified"]))
        except (TypeError, ValueError):
            modified_date = None
    clean = ""
    wc = 0
    chash = ""
    scraped_at: datetime | None = None
    content_block = post.get("content")
    if isinstance(content_block, dict):
        rendered = content_block.get("rendered")
        if isinstance(rendered, str) and rendered:
            clean = extract_article_text_from_rest(rendered)
            wc = word_count(clean)
            chash = compute_content_hash(clean)
            scraped_at = datetime.now(UTC)
    return Article(
        id=stable_article_id(link),
        author_id=author_id,
        url=link,  # type: ignore[arg-type]
        title=title,
        published_date=published,
        clean_text=clean,
        word_count=wc,
        metadata={},
        content_hash=chash,
        modified_date=modified_date,
        modifier_user_id=_modifier_user_id_from_post(post),
        scraped_at=scraped_at,
    )


def _user_dict_to_manifest(
    user: dict[str, object],
    *,
    total_posts: int,
    discovered_at: datetime,
) -> AuthorManifest:
    return AuthorManifest(
        wp_id=int(user["id"]),
        name=str(user["name"]),
        slug=str(user["slug"]),
        total_posts=total_posts,
        discovered_at=discovered_at,
    )


def _int_header(response: httpx.Response, name: str, default: int | None = None) -> int | None:
    raw = response.headers.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _author_config_from_manifest(m: AuthorManifest) -> AuthorConfig:
    """Build ``AuthorConfig`` for corpus-wide metadata ingestion.

    Baseline dates are wide placeholders; downstream analysis should filter or
    override using ``config.toml`` targets when needed.
    """
    return AuthorConfig(
        name=m.name,
        slug=m.slug,
        outlet="mediaite.com",
        role="target",
        archive_url=f"https://www.mediaite.com/author/{m.slug}/",
        baseline_start=date(1990, 1, 1),
        baseline_end=date(2035, 12, 31),
    )


def _load_authors_manifest(path: Path) -> dict[str, AuthorManifest]:
    """Load ``slug -> AuthorManifest`` from JSONL."""
    if not path.is_file():
        return {}
    out: dict[str, AuthorManifest] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            m = AuthorManifest.model_validate_json(line)
            out[m.slug] = m
    return out


def _write_authors_manifest(path: Path, rows: list[AuthorManifest]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(row.model_dump_json() + "\n")


async def discover_authors(
    settings: ForensicsSettings,
    *,
    force_refresh: bool = False,
    manifest_path: Path | None = None,
    errors_path: Path | None = None,
    post_year_min: int | None = None,
    post_year_max: int | None = None,
) -> int:
    """
    Discover all WordPress users and write ``data/authors_manifest.jsonl``.

    Returns the number of author rows written. Skips when the manifest exists unless
    ``force_refresh`` is True.
    """
    root = get_project_root()
    manifest = manifest_path or (root / "data/authors_manifest.jsonl")
    errors = errors_path or (root / "data/scrape_errors.jsonl")

    if manifest.exists() and not force_refresh:
        logger.info(
            "Skipping author discovery: %s exists (use --force-refresh to overwrite)",
            manifest,
        )
        return 0

    scraping = settings.scraping
    year_window = resolve_posts_year_window(
        scraping, override_min=post_year_min, override_max=post_year_max
    )
    posts_suffix = posts_year_query_fragment(*year_window) if year_window else ""
    if year_window:
        logger.info(
            "discover: WordPress posts limited to calendar years %d–%d (inclusive)",
            year_window[0],
            year_window[1],
        )
    else:
        logger.info("discover: WordPress posts date filter off (full published history)")
    limiter = RateLimiter(scraping.rate_limit_seconds, scraping.rate_limit_jitter)
    discovered_at = datetime.now(UTC)
    user_rows: list[dict[str, object]] = []

    async with create_scraping_client(scraping) as client:
        page = 1
        total_pages = 1
        while page <= total_pages:
            url = f"{MEDIAITE_REST}/users?per_page=100&page={page}"
            resp = await request_with_retry(
                client,
                limiter,
                scraping,
                "GET",
                url,
                errors_path=errors,
                phase="discover_users",
            )
            if not resp.is_success:
                await log_scrape_error(
                    errors,
                    url,
                    resp.status_code,
                    f"{resp.reason_phrase} (users page {page})",
                    "discover_users",
                )
                break
            tp = _int_header(resp, "X-WP-TotalPages", 1)
            if tp is not None:
                total_pages = max(1, tp)
            chunk = resp.json()
            if not isinstance(chunk, list):
                logger.warning("Unexpected users JSON on page %s", page)
                break
            if not chunk:
                break
            user_rows.extend(chunk)  # type: ignore[arg-type]
            page += 1

        if not user_rows:
            logger.error("Author discovery fetched no users; manifest not written")
            return 0

        count_sem = asyncio.Semaphore(max(1, scraping.max_concurrent))

        async def _count_posts_for_user(user: dict[str, object]) -> AuthorManifest | None:
            async with count_sem:
                wp_id = int(user["id"])
                count_url = (
                    f"{MEDIAITE_REST}/posts?author={wp_id}&per_page=1&_fields=id{posts_suffix}"
                )
                cresp = await request_with_retry(
                    client,
                    limiter,
                    scraping,
                    "GET",
                    count_url,
                    errors_path=errors,
                    phase="discover_count",
                )
                total_posts = 0
                if cresp.is_success:
                    tt = _int_header(cresp, "X-WP-Total", 0)
                    total_posts = tt if tt is not None else 0
                else:
                    await log_scrape_error(
                        errors,
                        count_url,
                        cresp.status_code,
                        cresp.reason_phrase,
                        "discover_count",
                    )
                try:
                    return _user_dict_to_manifest(
                        user,
                        total_posts=total_posts,
                        discovered_at=discovered_at,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning("Skipping malformed user row: %s", exc)
                    return None

        count_results = await asyncio.gather(*(_count_posts_for_user(u) for u in user_rows))
        manifests = [m for m in count_results if m is not None]

        manifests.sort(key=lambda m: m.total_posts, reverse=True)
        _write_authors_manifest(manifest, manifests)

        top = ", ".join(f"{m.name} ({m.total_posts})" for m in manifests[:10])
        logger.info("Discovered %s authors; top by posts: %s", len(manifests), top)
        return len(manifests)


async def collect_article_metadata(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    manifest_path: Path | None = None,
    errors_path: Path | None = None,
    repo: Repository | None = None,
    all_authors: bool = False,
    post_year_min: int | None = None,
    post_year_max: int | None = None,
) -> int:
    """
    Upsert authors and their posts (metadata only) into SQLite.

    When ``all_authors`` is False, only ``settings.authors`` are processed.
    When True, every author in ``authors_manifest.jsonl`` is ingested (still
    requires a prior ``discover_authors`` run to build the manifest).

    Returns the number of new article rows inserted (skips when URL already exists).
    """
    root = get_project_root()
    manifest = manifest_path or (root / "data/authors_manifest.jsonl")
    errors = errors_path or (root / "data/scrape_errors.jsonl")

    if not manifest.is_file():
        msg = f"Author manifest not found: {manifest}"
        raise FileNotFoundError(msg)

    by_slug = _load_authors_manifest(manifest)
    if all_authors:
        manifests_sorted = sorted(by_slug.values(), key=lambda x: x.slug)
        author_cfgs = [_author_config_from_manifest(m) for m in manifests_sorted]
        logger.info(
            "metadata: all-authors mode (%d author(s) from manifest; config author list ignored)",
            len(author_cfgs),
        )
    else:
        author_cfgs = list(settings.authors)
    scraping = settings.scraping
    year_window = resolve_posts_year_window(
        scraping, override_min=post_year_min, override_max=post_year_max
    )
    posts_suffix = posts_year_query_fragment(*year_window) if year_window else ""
    if year_window:
        logger.info(
            "metadata: WordPress posts limited to calendar years %d–%d (inclusive)",
            year_window[0],
            year_window[1],
        )
    else:
        logger.info("metadata: WordPress posts date filter off (full published history)")
    # One RateLimiter for the whole metadata run: parallel author tasks all call
    # request_with_retry with this instance, so inter-request spacing is global.
    limiter = RateLimiter(scraping.rate_limit_seconds, scraping.rate_limit_jitter)

    async def _run(r: Repository) -> int:
        db_lock = asyncio.Lock()
        author_sem = asyncio.Semaphore(max(1, scraping.max_concurrent))

        async def _ingest_one(cfg: AuthorConfig) -> int:
            async with author_sem:
                try:
                    return await _ingest_author_posts(
                        client,
                        limiter,
                        scraping,
                        r,
                        cfg,
                        by_slug,
                        errors,
                        db_lock,
                        posts_query_suffix=posts_suffix,
                    )
                except Exception as exc:  # noqa: BLE001 — isolate per-author failures
                    logger.exception("metadata ingestion failed for author slug=%s", cfg.slug)
                    await log_scrape_error(
                        errors,
                        cfg.archive_url,
                        None,
                        f"{cfg.slug}: {exc!r}",
                        "metadata_author",
                    )
                    return 0

        async with create_scraping_client(scraping) as client:
            results = await asyncio.gather(*(_ingest_one(cfg) for cfg in author_cfgs))
        return sum(results)

    with ensure_repo(db_path, repo) as r:
        return await _run(r)


async def _ingest_author_posts(
    client: httpx.AsyncClient,
    limiter: RateLimiter,
    scraping: ScrapingConfig,
    repo: Repository,
    cfg: AuthorConfig,
    by_slug: dict[str, AuthorManifest],
    errors_path: Path,
    db_lock: asyncio.Lock,
    *,
    posts_query_suffix: str = "",
) -> int:
    manifest_row = by_slug.get(cfg.slug)
    if manifest_row is None:
        await log_scrape_error(
            errors_path,
            "",
            None,
            f"slug_not_in_manifest:{cfg.slug}",
            "metadata",
        )
        return 0

    inserted_here = 0
    author = Author(
        id=_stable_author_id(cfg.slug),
        name=manifest_row.name,
        slug=cfg.slug,
        outlet=cfg.outlet,
        role=cfg.role,
        baseline_start=cfg.baseline_start,
        baseline_end=cfg.baseline_end,
        archive_url=cfg.archive_url,
    )
    async with db_lock:
        await asyncio.to_thread(repo.upsert_author, author)
    author_id = author.id

    wp_id = manifest_row.wp_id
    page = 1
    total_pages = 1
    published_dates: list[datetime] = []
    fields = "id,slug,link,title,date,modified,meta"
    if scraping.bulk_fetch_mode:
        fields += ",content"

    while page <= total_pages:
        url = (
            f"{MEDIAITE_REST}/posts?author={wp_id}&per_page=100&page={page}"
            f"&_fields={fields}"
            f"{posts_query_suffix}"
        )
        resp = await request_with_retry(
            client,
            limiter,
            scraping,
            "GET",
            url,
            errors_path=errors_path,
            phase="metadata",
        )
        if not resp.is_success:
            await log_scrape_error(
                errors_path,
                url,
                resp.status_code,
                f"{resp.reason_phrase} (author={cfg.slug} posts page {page})",
                "metadata",
            )
            break
        tp = _int_header(resp, "X-WP-TotalPages", 1)
        if tp is not None:
            total_pages = max(1, tp)
        raw = resp.json()
        if not isinstance(raw, list) or not raw:
            break
        posts = raw
        for post in posts:
            if not isinstance(post, dict):
                continue
            article = _wp_post_to_article(post, author_id)
            published_dates.append(article.published_date)
            url_s = str(article.url)
            async with db_lock:
                exists = await asyncio.to_thread(repo.article_url_exists, url_s)
                if not exists:
                    await asyncio.to_thread(repo.upsert_article, article)
                    inserted_here += 1
                elif scraping.bulk_fetch_mode and article.clean_text:
                    # Resume case: metadata-only row already present, upgrade it with
                    # the body text we just got from content.rendered.
                    existing = await asyncio.to_thread(repo.get_article_by_id, article.id)
                    if existing is not None and not existing.clean_text.strip():
                        upgraded = existing.with_updates(
                            clean_text=article.clean_text,
                            word_count=article.word_count,
                            content_hash=article.content_hash,
                            scraped_at=article.scraped_at,
                        )
                        await asyncio.to_thread(repo.upsert_article, upgraded)
        page += 1

    n_indexed = len(published_dates)
    if published_dates:
        lo = min(published_dates).date().isoformat()
        hi = max(published_dates).date().isoformat()
        logger.info("%s articles indexed for %s (%s–%s)", n_indexed, manifest_row.name, lo, hi)
    else:
        logger.info("%s articles indexed for %s (no dates)", n_indexed, manifest_row.name)
    return inserted_here


def _iter_manifests_from_users_json(
    users: list[dict[str, object]],
    *,
    total_posts_by_id: dict[int, int],
    discovered_at: datetime | None = None,
) -> Iterator[AuthorManifest]:
    """Build manifests from static user JSON and post-count map (tests / tooling)."""
    when = discovered_at or datetime.now(UTC)
    for u in users:
        wp_id = int(u["id"])
        tp = total_posts_by_id.get(wp_id, 0)
        yield _user_dict_to_manifest(u, total_posts=tp, discovered_at=when)
