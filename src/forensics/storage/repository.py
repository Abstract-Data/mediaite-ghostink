"""SQLite persistence for authors and articles."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType
from typing import NamedTuple
from uuid import uuid4

from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.json_io import ensure_parent
from forensics.storage.migrations import apply_migrations as _apply_sqlite_migrations
from forensics.utils.datetime import parse_datetime
from forensics.utils.hashing import SIMHASH_FINGERPRINT_VERSION

logger = logging.getLogger(__name__)

__all__ = [
    "Repository",
    "RepositoryReader",
    "UnfetchedArticle",
    "UnfetchedUrl",
    "ensure_repo",
    "init_db",
    "insert_analysis_run",
    "open_repository_connection",
]


class UnfetchedUrl(NamedTuple):
    """Article id and URL where body text has not been fetched yet."""

    article_id: str
    url: str


class UnfetchedArticle(NamedTuple):
    """Row needed to resume HTML fetch for one article."""

    article_id: str
    url: str
    author_name: str
    published_date: datetime


_SCHEMA = """
CREATE TABLE IF NOT EXISTS authors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    outlet TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('target', 'control')),
    baseline_start DATE,
    baseline_end DATE,
    archive_url TEXT NOT NULL,
    is_shared_byline INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL REFERENCES authors(id),
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    published_date DATETIME NOT NULL,
    raw_html_path TEXT,
    clean_text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    metadata JSON,
    content_hash TEXT NOT NULL,
    modified_date TEXT,
    modifier_user_id INTEGER,
    scraped_at TEXT,
    is_duplicate INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_articles_author_date ON articles(author_id, published_date);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    config_hash TEXT NOT NULL,
    description TEXT
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite with DEFERRED, WAL, busy timeout, and foreign keys (ADR-005).

    ``check_same_thread=False`` allows ``asyncio.to_thread`` workers to share the
    connection. :class:`Repository` serializes mutations with an internal lock;
    readers do not take that lock. WAL covers committed-read consistency; fan-out
    read load on one connection may still contend.
    """
    conn = sqlite3.connect(
        db_path,
        isolation_level="DEFERRED",
        timeout=30.0,
        check_same_thread=False,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def open_repository_connection(db_path: Path) -> sqlite3.Connection:
    """Open SQLite using the same connection policy as :class:`Repository` (WAL, busy timeout).

    For read-only helpers that should not create tables or hold a long-lived context.
    The caller must ``close()`` the connection when finished.
    """
    return _connect(Path(db_path))


def _migrate_articles_columns(conn: sqlite3.Connection) -> None:
    """Add Phase 3 columns to existing databases (idempotent)."""
    rows = conn.execute("PRAGMA table_info(articles)").fetchall()
    names = {str(r[1]) for r in rows}
    alters: list[str] = []
    if "modified_date" not in names:
        alters.append("ALTER TABLE articles ADD COLUMN modified_date TEXT;")
    if "modifier_user_id" not in names:
        alters.append("ALTER TABLE articles ADD COLUMN modifier_user_id INTEGER;")
    if "scraped_at" not in names:
        alters.append("ALTER TABLE articles ADD COLUMN scraped_at TEXT;")
    if "is_duplicate" not in names:
        alters.append("ALTER TABLE articles ADD COLUMN is_duplicate INTEGER NOT NULL DEFAULT 0;")
    for stmt in alters:
        conn.execute(stmt)


def _author_row_to_model(row: sqlite3.Row) -> Author:
    """Map an ``authors`` table row to :class:`Author`."""
    # Migration 001 adds ``is_shared_byline``; hand-built sqlite3.Row fixtures may omit it.
    keys = set(row.keys())
    shared = bool(row["is_shared_byline"]) if "is_shared_byline" in keys else False
    return Author(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        outlet=row["outlet"],
        role=row["role"],
        baseline_start=date.fromisoformat(str(row["baseline_start"])),
        baseline_end=date.fromisoformat(str(row["baseline_end"])),
        archive_url=row["archive_url"],
        is_shared_byline=shared,
    )


def _validate_batch_size(batch_size: int) -> None:
    if batch_size < 1:
        msg = f"batch_size must be >= 1, got {batch_size}"
        raise ValueError(msg)


def _row_to_article(row: sqlite3.Row) -> Article:
    metadata_raw = row["metadata"]
    if metadata_raw:
        try:
            metadata = json.loads(metadata_raw)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed article metadata JSON for id=%s", row["id"])
            metadata = {}
    else:
        metadata = {}
    modified_raw = row["modified_date"] if row["modified_date"] is not None else None
    mod_dt = parse_datetime(modified_raw) if modified_raw else None
    scraped_raw = row["scraped_at"] if row["scraped_at"] is not None else None
    scraped_dt = parse_datetime(scraped_raw) if scraped_raw else None
    mod_uid = row["modifier_user_id"]
    is_dup = bool(row["is_duplicate"])
    return Article(
        id=row["id"],
        author_id=row["author_id"],
        url=row["url"],
        title=row["title"],
        published_date=parse_datetime(row["published_date"]),
        raw_html_path=row["raw_html_path"] or "",
        clean_text=row["clean_text"] or "",
        word_count=int(row["word_count"]),
        metadata=metadata,
        content_hash=row["content_hash"] or "",
        modified_date=mod_dt,
        modifier_user_id=int(mod_uid) if mod_uid is not None else None,
        scraped_at=scraped_dt,
        is_duplicate=is_dup,
    )


class RepositoryReader:
    """Read-only queries and iterators mixed into :class:`Repository`."""

    __slots__ = ()

    def get_author(self, author_id: str) -> Author | None:
        conn = self._require_conn()
        row = conn.execute("SELECT * FROM authors WHERE id = ?", (author_id,)).fetchone()
        if row is None:
            return None
        return _author_row_to_model(row)

    def get_author_by_slug(self, slug: str) -> Author | None:
        conn = self._require_conn()
        row = conn.execute("SELECT * FROM authors WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return None
        return _author_row_to_model(row)

    def all_authors(self) -> list[Author]:
        """Return every author in the database ordered by slug.

        Use inside an active ``with Repository(...)`` context (ADR-005).
        """
        conn = self._require_conn()
        rows = conn.execute("SELECT * FROM authors ORDER BY slug").fetchall()
        return [_author_row_to_model(row) for row in rows]

    def list_articles_for_extraction(self, *, author_id: str | None = None) -> list[Article]:
        """Return articles eligible for feature extraction.

        Non-empty body, not a redirect stub, not duplicate, minimum word count.
        """
        parts = [
            "length(trim(a.clean_text)) > 0",
            "instr(a.clean_text, '[REDIRECT:') != 1",
            "a.is_duplicate = 0",
            "a.word_count >= 50",
        ]
        params: tuple[str, ...] = ()
        if author_id is not None:
            parts.append("a.author_id = ?")
            params = (author_id,)
        where_sql = " AND ".join(parts)
        sql = f"SELECT a.* FROM articles a WHERE {where_sql} ORDER BY a.published_date"
        conn = self._require_conn()
        rows = conn.execute(sql, params).fetchall() if params else conn.execute(sql).fetchall()
        return [_row_to_article(row) for row in rows]

    def article_url_exists(self, url: str) -> bool:
        """Return True if an article with this canonical URL is already stored."""
        conn = self._require_conn()
        row = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
        return row is not None

    def get_article_by_id(self, article_id: str) -> Article | None:
        conn = self._require_conn()
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row is None:
            return None
        return _row_to_article(row)

    def get_articles_by_author(self, author_id: str) -> list[Article]:
        """Eager load — prefer :meth:`iter_articles_by_author` for large authors."""
        return list(self.iter_articles_by_author(author_id))

    def iter_articles_by_author(
        self, author_id: str, *, batch_size: int = 500
    ) -> Iterator[Article]:
        """Yield one author's articles in ``published_date`` order without full load."""
        _validate_batch_size(batch_size)
        conn = self._require_conn()
        cursor = conn.execute(
            "SELECT * FROM articles WHERE author_id = ? ORDER BY published_date",
            (author_id,),
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield _row_to_article(row)

    def get_all_articles(self) -> list[Article]:
        """Eager load — prefer :meth:`iter_all_articles` for the full corpus."""
        return list(self.iter_all_articles())

    def iter_all_articles(self, *, batch_size: int = 500) -> Iterator[Article]:
        """Yield every article in ``published_date`` order without loading the full table."""
        _validate_batch_size(batch_size)
        conn = self._require_conn()
        cursor = conn.execute("SELECT * FROM articles ORDER BY published_date")
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield _row_to_article(row)

    def iter_dedup_source_rows(
        self, *, batch_size: int = 500
    ) -> Iterator[tuple[str, datetime, str, str]]:
        """Yield ``(id, published_date, title, clean_text)`` for simhash deduplication.

        Matches the historical in-memory pool filter: non-empty body and not a
        ``[REDIRECT:`` prefix (same rules as ``deduplicate_articles``).
        """
        _validate_batch_size(batch_size)
        conn = self._require_conn()
        sql = """
            SELECT id, published_date, title, clean_text
            FROM articles
            WHERE clean_text IS NOT NULL
              AND clean_text != ''
              AND (length(clean_text) < 10 OR substr(clean_text, 1, 10) != '[REDIRECT:')
            ORDER BY published_date
        """
        cursor = conn.execute(sql)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield (
                    str(row["id"]),
                    parse_datetime(row["published_date"]),
                    str(row["title"]),
                    str(row["clean_text"]),
                )

    def iter_dedup_source_rows_with_fp_meta(
        self, *, batch_size: int = 500
    ) -> Iterator[tuple[str, datetime, str, str, str | None, str | None]]:
        """Like :meth:`iter_dedup_source_rows` but includes optional simhash cache columns."""
        _validate_batch_size(batch_size)
        conn = self._require_conn()
        keys = {str(r[1]) for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
        has_fp = "dedup_simhash" in keys and "dedup_simhash_version" in keys
        fp_sel = (
            "a.dedup_simhash AS dedup_simhash, a.dedup_simhash_version AS dedup_simhash_version"
        )
        if not has_fp:
            fp_sel = "NULL AS dedup_simhash, NULL AS dedup_simhash_version"
        sql = f"""
            SELECT a.id, a.published_date, a.title, a.clean_text, {fp_sel}
            FROM articles a
            WHERE a.clean_text IS NOT NULL
              AND a.clean_text != ''
              AND (length(a.clean_text) < 10 OR substr(a.clean_text, 1, 10) != '[REDIRECT:')
            ORDER BY a.published_date
        """
        cursor = conn.execute(sql)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                fp = row["dedup_simhash"]
                ver = row["dedup_simhash_version"]
                yield (
                    str(row["id"]),
                    parse_datetime(row["published_date"]),
                    str(row["title"]),
                    str(row["clean_text"]),
                    str(fp) if fp is not None else None,
                    str(ver) if ver is not None else None,
                )

    def load_dedup_simhashes(self) -> list[tuple[str, int]]:
        """Return ``(id, simhash)`` for rows whose version matches the current simhash fingerprint.

        Omits missing/stale versions (still eligible for
        :meth:`Repository.recompute_stale_dedup_simhashes`). Logs one warning
        count for stale in-corpus rows with dedup-eligible body text.
        """
        conn = self._require_conn()
        keys = {str(r[1]) for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
        if "dedup_simhash" not in keys or "dedup_simhash_version" not in keys:
            return []
        stale_sql = """
            SELECT COUNT(*) FROM articles
            WHERE clean_text IS NOT NULL
              AND clean_text != ''
              AND (length(clean_text) < 10 OR substr(clean_text, 1, 10) != '[REDIRECT:')
              AND dedup_simhash IS NOT NULL
              AND (
                    dedup_simhash_version IS NULL
                 OR dedup_simhash_version != ?
              )
        """
        stale_row = conn.execute(stale_sql, (SIMHASH_FINGERPRINT_VERSION,)).fetchone()
        stale_n = int(stale_row[0]) if stale_row else 0
        if stale_n:
            logger.warning(
                "dedup_simhash: excluding %d article(s) with stale or NULL fingerprint version "
                "from the cached simhash set; run `forensics dedup recompute-fingerprints`",
                stale_n,
            )
        rows = conn.execute(
            """
            SELECT id, dedup_simhash FROM articles
            WHERE clean_text IS NOT NULL
              AND clean_text != ''
              AND (length(clean_text) < 10 OR substr(clean_text, 1, 10) != '[REDIRECT:')
              AND dedup_simhash IS NOT NULL
              AND dedup_simhash_version = ?
            ORDER BY published_date
            """,
            (SIMHASH_FINGERPRINT_VERSION,),
        ).fetchall()
        out: list[tuple[str, int]] = []
        for row in rows:
            raw = row["dedup_simhash"]
            if raw is None:
                continue
            try:
                out.append((str(row["id"]), int(str(raw), 16)))
            except ValueError:
                logger.warning("dedup_simhash: skipping malformed hex for id=%s", row["id"])
        return out

    def get_unfetched_urls(self) -> list[UnfetchedUrl]:
        """Return rows where body text has not been fetched yet."""
        conn = self._require_conn()
        rows = conn.execute(
            "SELECT id, url FROM articles WHERE clean_text = '' OR clean_text IS NULL"
        ).fetchall()
        return [UnfetchedUrl(str(r[0]), str(r[1])) for r in rows]

    def list_unfetched_for_fetch(self) -> list[UnfetchedArticle]:
        """Return unfetched articles with author name and publish date for fetch ordering."""
        conn = self._require_conn()
        rows = conn.execute(
            """
            SELECT a.id, a.url, au.name AS author_name, a.published_date
            FROM articles a
            JOIN authors au ON a.author_id = au.id
            WHERE a.clean_text = '' OR a.clean_text IS NULL
            ORDER BY a.published_date
            """
        ).fetchall()
        return [
            UnfetchedArticle(
                str(row["id"]),
                str(row["url"]),
                str(row["author_name"]),
                parse_datetime(row["published_date"]),
            )
            for row in rows
        ]


class Repository(RepositoryReader):
    """SQLite access for authors and articles.

    Use as a context manager. Reads use :class:`RepositoryReader`; this class
    owns the connection, schema setup, migrations, and mutations (lock-serialized).
    """

    __slots__ = ("_db_path", "_conn", "_lock")

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def __enter__(self) -> Repository:
        ensure_parent(self._db_path)
        self._conn = _connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            _migrate_articles_columns(self._conn)
            self._conn.commit()
            _apply_sqlite_migrations(self._conn)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            with self._lock:
                if exc is not None:
                    self._conn.rollback()
                else:
                    self._conn.commit()
                self._conn.close()
            self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            msg = "Repository is not in an active session; use `with Repository(path) as repo:`"
            raise RuntimeError(msg)
        return self._conn

    def ensure_schema(self) -> None:
        """Create tables if missing (requires active ``with`` session)."""
        conn = self._require_conn()
        with self._lock:
            conn.executescript(_SCHEMA)
            _migrate_articles_columns(conn)

    def apply_migrations(self) -> list[int]:
        """Run pending numbered SQLite migrations; return newly applied version ints.

        Also invoked from ``Repository.__enter__``; idempotent per migration.
        """
        conn = self._require_conn()
        with self._lock:
            return _apply_sqlite_migrations(conn)

    def upsert_author(self, author: Author) -> None:
        conn = self._require_conn()
        with self._lock:
            conn.execute(
                """
            INSERT INTO authors (
                id, name, slug, outlet, role, baseline_start, baseline_end,
                archive_url, is_shared_byline
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                slug=excluded.slug,
                outlet=excluded.outlet,
                role=excluded.role,
                baseline_start=excluded.baseline_start,
                baseline_end=excluded.baseline_end,
                archive_url=excluded.archive_url,
                is_shared_byline=excluded.is_shared_byline
            """,
                (
                    author.id,
                    author.name,
                    author.slug,
                    author.outlet,
                    author.role,
                    author.baseline_start.isoformat(),
                    author.baseline_end.isoformat(),
                    author.archive_url,
                    int(author.is_shared_byline),
                ),
            )

    def upsert_article(self, article: Article) -> None:
        payload = article.model_dump(mode="json")
        metadata_json = json.dumps(payload.get("metadata") or {})
        modified = article.modified_date.isoformat() if article.modified_date else None
        scraped = article.scraped_at.isoformat() if article.scraped_at else None
        conn = self._require_conn()
        with self._lock:
            conn.execute(
                """
            INSERT INTO articles (
                id, author_id, url, title, published_date, raw_html_path,
                clean_text, word_count, metadata, content_hash,
                modified_date, modifier_user_id, scraped_at, is_duplicate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                author_id=excluded.author_id,
                url=excluded.url,
                title=excluded.title,
                published_date=excluded.published_date,
                raw_html_path=excluded.raw_html_path,
                clean_text=excluded.clean_text,
                word_count=excluded.word_count,
                metadata=excluded.metadata,
                content_hash=excluded.content_hash,
                modified_date=excluded.modified_date,
                modifier_user_id=excluded.modifier_user_id,
                scraped_at=excluded.scraped_at,
                is_duplicate=excluded.is_duplicate
            """,
                (
                    article.id,
                    article.author_id,
                    str(article.url),
                    article.title,
                    article.published_date.isoformat(),
                    article.raw_html_path or None,
                    article.clean_text,
                    article.word_count,
                    metadata_json,
                    article.content_hash,
                    modified,
                    article.modifier_user_id,
                    scraped,
                    1 if article.is_duplicate else 0,
                ),
            )

    def clear_duplicate_flags(self, article_ids: Iterable[str], *, chunk_size: int = 500) -> int:
        """Set ``is_duplicate = 0`` for the given ids.

        Returns number of rows touched (best-effort).
        """
        return self._bulk_set_is_duplicate(article_ids, 0, chunk_size=chunk_size)

    def mark_duplicates(self, article_ids: Iterable[str], *, chunk_size: int = 500) -> int:
        """Set ``is_duplicate = 1`` for the given ids.

        Returns number of rows touched (best-effort).
        """
        return self._bulk_set_is_duplicate(article_ids, 1, chunk_size=chunk_size)

    def dedup_simhash_columns_present(self) -> bool:
        """Return True when ``articles`` has dedup simhash columns (D-01 schema)."""
        conn = self._require_conn()
        keys = {str(r[1]) for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
        return "dedup_simhash" in keys and "dedup_simhash_version" in keys

    def recompute_stale_dedup_simhashes(self, *, limit: int | None = None) -> dict[str, int]:
        """Recompute simhash + version for articles not stamped at the current version.

        Runs inside a single ``BEGIN IMMEDIATE`` transaction (mirrors duplicate
        flag updates). Returns counts ``recomputed``, ``skipped``, ``errors``.
        """
        from forensics.utils.hashing import simhash

        conn = self._require_conn()
        if not self.dedup_simhash_columns_present():
            return {"recomputed": 0, "skipped": 0, "errors": 0}

        sql = """
            SELECT id, clean_text FROM articles
            WHERE clean_text IS NOT NULL
              AND clean_text != ''
              AND (length(clean_text) < 10 OR substr(clean_text, 1, 10) != '[REDIRECT:')
              AND (
                    dedup_simhash_version IS NULL
                 OR dedup_simhash_version != ?
              )
            ORDER BY published_date
        """
        params: tuple[object, ...] = (SIMHASH_FINGERPRINT_VERSION,)
        if limit is not None:
            sql = f"{sql}\nLIMIT ?"
            params = (SIMHASH_FINGERPRINT_VERSION, int(limit))

        recomputed = 0
        errors = 0
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = conn.execute(sql, params).fetchall()
                for row in rows:
                    aid = str(row["id"])
                    text = str(row["clean_text"])
                    try:
                        fp = simhash(text)
                    except Exception:
                        logger.exception("dedup recompute: simhash failed for id=%s", aid)
                        errors += 1
                        continue
                    conn.execute(
                        """
                        UPDATE articles
                        SET dedup_simhash = ?, dedup_simhash_version = ?
                        WHERE id = ?
                        """,
                        (format(fp, "x"), SIMHASH_FINGERPRINT_VERSION, aid),
                    )
                    recomputed += 1
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
        return {"recomputed": recomputed, "skipped": 0, "errors": errors}

    def apply_duplicate_flags_transaction(
        self,
        clear_ids: Iterable[str],
        mark_duplicate_ids: Iterable[str],
        *,
        chunk_size: int = 500,
    ) -> tuple[int, int]:
        """Atomically clear then mark duplicate flags in one ``BEGIN IMMEDIATE`` transaction."""
        clear_list = list(clear_ids)
        mark_list = list(mark_duplicate_ids)
        if chunk_size < 1:
            msg = f"chunk_size must be >= 1, got {chunk_size}"
            raise ValueError(msg)
        conn = self._require_conn()
        cleared = 0
        marked = 0
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cleared = self._bulk_set_is_duplicate_on_conn(
                    conn, clear_list, 0, chunk_size=chunk_size
                )
                marked = self._bulk_set_is_duplicate_on_conn(
                    conn, mark_list, 1, chunk_size=chunk_size
                )
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
        return cleared, marked

    @staticmethod
    def _bulk_set_is_duplicate_on_conn(
        conn: sqlite3.Connection,
        article_ids: list[str],
        value: int,
        *,
        chunk_size: int,
    ) -> int:
        if not article_ids:
            return 0
        total = 0
        for i in range(0, len(article_ids), chunk_size):
            chunk = article_ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cur = conn.execute(
                f"UPDATE articles SET is_duplicate = ? WHERE id IN ({placeholders})",
                (value, *chunk),
            )
            if cur.rowcount >= 0:
                total += cur.rowcount
        return total

    def _bulk_set_is_duplicate(
        self, article_ids: Iterable[str], value: int, *, chunk_size: int
    ) -> int:
        ids = list(article_ids)
        if not ids:
            return 0
        if chunk_size < 1:
            msg = f"chunk_size must be >= 1, got {chunk_size}"
            raise ValueError(msg)
        conn = self._require_conn()
        total = 0
        with self._lock:
            total = self._bulk_set_is_duplicate_on_conn(conn, ids, value, chunk_size=chunk_size)
        return total

    def rewrite_raw_paths_after_archive(self, year: int) -> int:
        """Rewrite ``raw_html_path`` after year folder is archived to a tar member ref.

        Rejects rows whose tail contains path separators or ``..`` so the rewritten
        reference cannot escape the ``raw/{year}.tar.gz:`` archive root even if the
        stored path was tampered with.
        """
        if not isinstance(year, int) or year < 1000 or year > 9999:
            msg = f"archive year must be 4-digit int: {year!r}"
            raise ValueError(msg)
        prefix = f"raw/{year}/"
        archive_ref = f"raw/{year}.tar.gz"
        conn = self._require_conn()
        with self._lock:
            rows = conn.execute(
                "SELECT id, raw_html_path FROM articles WHERE raw_html_path LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
            n = 0
            for aid, old in rows:
                if not old or not isinstance(old, str) or not old.startswith(prefix):
                    continue
                tail = old[len(prefix) :]
                if not tail or "/" in tail or "\\" in tail or tail.startswith(".."):
                    continue
                new_path = f"{archive_ref}:{tail}"
                conn.execute(
                    "UPDATE articles SET raw_html_path = ? WHERE id = ?",
                    (new_path, aid),
                )
                n += 1
            return n

    def insert_analysis_run_row(self, *, config_hash: str, description: str = "") -> str:
        """Insert one ``analysis_runs`` row; returns new run id."""
        rid = str(uuid4())
        ts = datetime.now(UTC).isoformat()
        conn = self._require_conn()
        with self._lock:
            conn.execute(
                "INSERT INTO analysis_runs "
                "(id, timestamp, config_hash, description) VALUES (?,?,?,?)",
                (rid, ts, config_hash, description),
            )
        return rid


@contextmanager
def ensure_repo(db_path: Path, repo: Repository | None = None) -> Iterator[Repository]:
    """Yield an active :class:`Repository`, opening one if not provided."""
    if repo is not None:
        yield repo
    else:
        with Repository(db_path) as owned:
            yield owned


def init_db(db_path: Path) -> None:
    """Create database tables if they do not exist."""
    with Repository(db_path):
        pass


def insert_analysis_run(
    db_path: Path,
    *,
    config_hash: str,
    description: str = "",
) -> str:
    """Insert one row into ``analysis_runs`` (pipeline audit trail). Returns run id."""
    with Repository(db_path) as repo:
        return repo.insert_analysis_run_row(config_hash=config_hash, description=description)
