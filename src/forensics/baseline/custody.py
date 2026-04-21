"""Raw archive integrity checks (Phase 10)."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from forensics.utils.provenance import audit_scrape_timestamps

logger = logging.getLogger(__name__)

_YEAR_TAR = re.compile(r"^(\d{4})\.tar\.gz$")


def verify_raw_archive_integrity(data_dir: Path) -> bool:
    """Check ``data/raw/{year}.tar.gz`` vs latest ``scraped_at`` for rows pointing at that archive.

    Matches ``raw/{year}.tar.gz:`` prefixes on ``articles.raw_html_path`` and compares mtimes.
    """
    raw = data_dir / "raw"
    db_path = data_dir / "articles.db"
    if not raw.is_dir():
        return True
    if not db_path.is_file():
        logger.warning("verify_raw_archive_integrity: no database at %s", db_path)
        return True

    ok = True
    for tar in sorted(raw.glob("*.tar.gz")):
        m = _YEAR_TAR.match(tar.name)
        if not m:
            continue
        year = m.group(1)
        like_pat = f"raw/{year}.tar.gz:%"
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                """
                SELECT MAX(scraped_at) AS mx FROM articles
                WHERE raw_html_path LIKE ? AND scraped_at IS NOT NULL AND TRIM(scraped_at) != ''
                """,
                (like_pat,),
            ).fetchone()
        finally:
            conn.close()
        if row is None or row[0] is None:
            logger.info("verify_raw_archive: no scraped_at rows for archive %s", tar.name)
            continue
        try:
            latest = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=UTC)
        except ValueError:
            continue
        mtime = datetime.fromtimestamp(tar.stat().st_mtime, tz=UTC)
        if latest > mtime and (latest - mtime).total_seconds() > 86400 * 7:
            logger.error(
                "verify_raw_archive: %s mtime %s is more than 7 days older than latest scrape %s",
                tar.name,
                mtime.isoformat(),
                latest.isoformat(),
            )
            ok = False
    return ok


__all__ = ["audit_scrape_timestamps", "verify_raw_archive_integrity"]
