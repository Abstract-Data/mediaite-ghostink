"""SQLite persistence for authors and articles."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NamedTuple

from forensics.models.article import Article
from forensics.models.author import Author
from forensics.utils.datetime import parse_datetime


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
    """Open SQLite with DEFERRED transactions, WAL, and busy timeout (ADR-001)."""
    conn = sqlite3.connect(db_path, isolation_level="DEFERRED", timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def _db_session(db_path: Path) -> Generator[sqlite3.Connection]:
    """Yield a connection with Row factory; commit on success, rollback on error."""
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def init_db(db_path: Path) -> None:
    """Create database tables if they do not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _db_session(db_path) as conn:
        conn.executescript(_SCHEMA)
        _migrate_articles_columns(conn)


def insert_analysis_run(
    db_path: Path,
    *,
    config_hash: str,
    description: str = "",
) -> str:
    """Insert one row into ``analysis_runs`` (pipeline audit trail). Returns run id."""
    init_db(db_path)
    rid = str(uuid.uuid4())
    ts = datetime.now(UTC).isoformat()
    with _db_session(db_path) as conn:
        conn.execute(
            "INSERT INTO analysis_runs (id, timestamp, config_hash, description) VALUES (?,?,?,?)",
            (rid, ts, config_hash, description),
        )
    return rid


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


class Repository:
    """SQLite access for authors and articles (one connection + transaction per method)."""

    __slots__ = ("_db_path",)

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def get_author(self, author_id: str) -> Author | None:
        with _db_session(self._db_path) as conn:
            row = conn.execute("SELECT * FROM authors WHERE id = ?", (author_id,)).fetchone()
        if row is None:
            return None
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

    def upsert_author(self, author: Author) -> None:
        with _db_session(self._db_path) as conn:
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

    def article_url_exists(self, url: str) -> bool:
        """Return True if an article with this canonical URL is already stored."""
        with _db_session(self._db_path) as conn:
            row = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
        return row is not None

    def upsert_article(self, article: Article) -> None:
        payload = article.model_dump(mode="json")
        metadata_json = json.dumps(payload.get("metadata") or {})
        modified = article.modified_date.isoformat() if article.modified_date else None
        scraped = article.scraped_at.isoformat() if article.scraped_at else None
        with _db_session(self._db_path) as conn:
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

    def get_article_by_id(self, article_id: str) -> Article | None:
        with _db_session(self._db_path) as conn:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row is None:
            return None
        return _row_to_article(row)

    def get_articles_by_author(self, author_id: str) -> list[Article]:
        with _db_session(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE author_id = ? ORDER BY published_date",
                (author_id,),
            ).fetchall()
        return [_row_to_article(row) for row in rows]

    def get_all_articles(self) -> list[Article]:
        with _db_session(self._db_path) as conn:
            rows = conn.execute("SELECT * FROM articles ORDER BY published_date").fetchall()
        return [_row_to_article(row) for row in rows]

    def get_unfetched_urls(self) -> list[UnfetchedUrl]:
        """Return rows where body text has not been fetched yet."""
        with _db_session(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, url FROM articles WHERE clean_text = '' OR clean_text IS NULL"
            ).fetchall()
        return [UnfetchedUrl(str(r[0]), str(r[1])) for r in rows]

    def list_unfetched_for_fetch(self) -> list[UnfetchedArticle]:
        """Return unfetched articles with author name and publish date for fetch ordering."""
        with _db_session(self._db_path) as conn:
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

    def rewrite_raw_paths_after_archive(self, year: int) -> int:
        """Rewrite ``raw_html_path`` after year folder is archived to a tar member ref."""
        prefix = f"raw/{year}/"
        archive_ref = f"raw/{year}.tar.gz"
        with _db_session(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, raw_html_path FROM articles WHERE raw_html_path LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
            n = 0
            for aid, old in rows:
                if not old or not isinstance(old, str) or not old.startswith(prefix):
                    continue
                tail = old[len(prefix) :]
                new_path = f"{archive_ref}:{tail}"
                conn.execute(
                    "UPDATE articles SET raw_html_path = ? WHERE id = ?",
                    (new_path, aid),
                )
                n += 1
            return n
