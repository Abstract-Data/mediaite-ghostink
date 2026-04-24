"""SQLite persistence for authors and articles."""

from __future__ import annotations

import json
import sqlite3
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
    archive_url TEXT NOT NULL
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
    """Open SQLite with DEFERRED transactions, WAL, and busy timeout (ADR-005).

    Threading contract (P1-SEC-001):

    - ``check_same_thread=False`` is set so asyncio worker threads
      (``asyncio.to_thread``) can share one connection with the coroutine that
      created it. SQLite itself serializes access at the C level, but Python's
      cursor objects and transaction state are NOT safe for concurrent use.
    - **Callers MUST serialize all reads and writes with an external lock.**
      The scraper's ``db_lock = asyncio.Lock()`` is the canonical example (see
      ``forensics.scraper.crawler._ingest_author_posts`` and
      ``forensics.scraper.fetcher._handle_success``). Typical pattern::

          async with db_lock:
              await asyncio.to_thread(repo.upsert_article, article)

    - Skipping the lock can corrupt the WAL journal (partial writes from one
      thread seen by another mid-transaction) and will manifest as
      ``database is locked`` stalls or, worse, silent data loss. If you aren't
      writing the lock, you probably shouldn't be sharing the ``Repository``
      across workers.
    - The canonical single-threaded usage is the ``with Repository(db_path)
      as repo:`` context manager; only fan-out via ``asyncio.to_thread``
      needs the explicit lock.
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
    return Author(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        outlet=row["outlet"],
        role=row["role"],
        baseline_start=date.fromisoformat(str(row["baseline_start"])),
        baseline_end=date.fromisoformat(str(row["baseline_end"])),
        archive_url=row["archive_url"],
    )


def _validate_batch_size(batch_size: int) -> None:
    if batch_size < 1:
        msg = f"batch_size must be >= 1, got {batch_size}"
        raise ValueError(msg)


def _row_to_article(row: sqlite3.Row) -> Article:
    metadata_raw = row["metadata"]
    metadata: dict[str, object] = json.loads(metadata_raw) if metadata_raw else {}
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
    """Read-only queries and iterators mixed into :class:`Repository` (P2-ARCH-001)."""

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
        """Return articles eligible for feature extraction (Phase 4 selection rules)."""
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

    Use as a context manager to hold one connection for a batch of operations::

        with Repository(db_path) as repo:
            repo.upsert_article(...)

    Read/query methods live on :class:`RepositoryReader` (P2-ARCH-001); this class
    holds connection lifecycle, schema, and mutation APIs.
    """

    __slots__ = ("_db_path", "_conn")

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        return self._db_path

    def __enter__(self) -> Repository:
        ensure_parent(self._db_path)
        self._conn = _connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        _migrate_articles_columns(self._conn)
        self._conn.commit()
        # Phase 15 Step 0.2 — forward-only numbered migrations (schema_version
        # bookkeeping). Safe to run on every open; each migration is idempotent.
        _apply_sqlite_migrations(self._conn)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
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
        conn.executescript(_SCHEMA)
        _migrate_articles_columns(conn)

    def apply_migrations(self) -> list[int]:
        """Run pending forward-only numbered migrations (Phase 15 Step 0.2).

        Returns the versions newly applied (empty list when the DB is already
        up-to-date). Intended for CLI use (``forensics migrate``); the
        ``Repository`` context manager also calls this on every open, so
        application code rarely needs to invoke it directly.
        """
        conn = self._require_conn()
        return _apply_sqlite_migrations(conn)

    def upsert_author(self, author: Author) -> None:
        conn = self._require_conn()
        conn.execute(
            """
            INSERT INTO authors (
                id, name, slug, outlet, role, baseline_start, baseline_end, archive_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                slug=excluded.slug,
                outlet=excluded.outlet,
                role=excluded.role,
                baseline_start=excluded.baseline_start,
                baseline_end=excluded.baseline_end,
                archive_url=excluded.archive_url
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
            ),
        )

    def upsert_article(self, article: Article) -> None:
        payload = article.model_dump(mode="json")
        metadata_json = json.dumps(payload.get("metadata") or {})
        modified = article.modified_date.isoformat() if article.modified_date else None
        scraped = article.scraped_at.isoformat() if article.scraped_at else None
        conn = self._require_conn()
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
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cur = conn.execute(
                f"UPDATE articles SET is_duplicate = ? WHERE id IN ({placeholders})",
                (value, *chunk),
            )
            if cur.rowcount >= 0:
                total += cur.rowcount
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
        conn.execute(
            "INSERT INTO analysis_runs (id, timestamp, config_hash, description) VALUES (?,?,?,?)",
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
