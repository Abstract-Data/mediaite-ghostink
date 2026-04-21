"""Deterministic hashes and chain-of-custody helpers for forensic reporting."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forensics.config.settings import ForensicsSettings

CUSTODY_FILENAME = "corpus_custody.json"


def compute_config_hash(settings: ForensicsSettings) -> str:
    """Deterministic short hash of the pipeline configuration."""
    payload = settings.model_dump(mode="json", exclude={"db_path"})
    config_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(config_str.encode()).hexdigest()[:12]


def compute_corpus_hash(db_path: Path) -> str:
    """SHA-256 of ordered ``content_hash`` values from the articles table (full hex digest)."""
    if not db_path.is_file():
        return hashlib.sha256(b"").hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        hashes = conn.execute(
            "SELECT content_hash FROM articles ORDER BY id",
        ).fetchall()
    finally:
        conn.close()
    combined = "|".join(h[0] for h in hashes if h[0])
    return hashlib.sha256(combined.encode()).hexdigest()


def get_run_metadata(settings: ForensicsSettings) -> dict[str, str]:
    """Metadata dict for notebook headers and manifests."""
    import sys

    return {
        "config_hash": compute_config_hash(settings),
        "corpus_hash": compute_corpus_hash(settings.db_path),
        "timestamp": datetime.now(UTC).isoformat(),
        "python_version": sys.version,
    }


def write_corpus_custody(db_path: Path, analysis_dir: Path) -> Path:
    """Record corpus hash at end of analysis for ``report --verify``."""
    analysis_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "corpus_hash": compute_corpus_hash(db_path),
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    path = analysis_dir / CUSTODY_FILENAME
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_corpus_custody(analysis_dir: Path) -> dict[str, Any] | None:
    """Load stored custody record if present."""
    path = analysis_dir / CUSTODY_FILENAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def verify_corpus_hash(db_path: Path, analysis_dir: Path) -> tuple[bool, str]:
    """Return (ok, message) comparing live corpus hash to custody file."""
    current = compute_corpus_hash(db_path)
    rec = load_corpus_custody(analysis_dir)
    if rec is None:
        return False, f"No custody record at {analysis_dir / CUSTODY_FILENAME}"
    expected = rec.get("corpus_hash")
    if expected != current:
        return (
            False,
            f"Corpus hash mismatch: stored={expected!r} current={current!r}",
        )
    return True, "Corpus hash matches custody record."


def audit_scrape_timestamps(db_path: Path) -> Mapping[str, Any]:
    """Summarize ``scraped_at`` coverage (Phase 8 notebooks + Phase 10 chain-of-custody)."""
    if not db_path.is_file():
        return {
            "articles_total": 0,
            "missing_scraped_at": 0,
            "duplicates_excluded": 0,
            "scraped_at_min": None,
            "scraped_at_max": None,
            "total_articles": 0,
            "articles_with_scraped_at": 0,
            "earliest_scrape": None,
            "latest_scrape": None,
            "scrape_duration_days": 0,
            "message": "database file not found",
        }
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS n,
              SUM(
                CASE WHEN scraped_at IS NULL OR TRIM(scraped_at) = ''
                THEN 1 ELSE 0 END
              ) AS missing,
              SUM(CASE WHEN is_duplicate != 0 THEN 1 ELSE 0 END) AS dups
            FROM articles
            """,
        ).fetchone()
        bounds = conn.execute(
            """
            SELECT MIN(scraped_at) AS mn, MAX(scraped_at) AS mx
            FROM articles
            WHERE scraped_at IS NOT NULL AND TRIM(scraped_at) != ''
            """,
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {
            "articles_total": 0,
            "missing_scraped_at": 0,
            "duplicates_excluded": 0,
            "scraped_at_min": None,
            "scraped_at_max": None,
            "total_articles": 0,
            "articles_with_scraped_at": 0,
            "earliest_scrape": None,
            "latest_scrape": None,
            "scrape_duration_days": 0,
            "message": "empty database",
        }
    total = int(row["n"] or 0)
    missing = int(row["missing"] or 0)
    mn = bounds["mn"] if bounds else None
    mx = bounds["mx"] if bounds else None
    duration_days = 0
    if mn and mx:
        try:
            from datetime import datetime

            a = datetime.fromisoformat(str(mn).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(mx).replace("Z", "+00:00"))
            duration_days = max(0, int((b - a).total_seconds() // 86400))
        except ValueError:
            duration_days = 0
    return {
        "articles_total": total,
        "missing_scraped_at": missing,
        "duplicates_excluded": int(row["dups"] or 0),
        "scraped_at_min": mn,
        "scraped_at_max": mx,
        "total_articles": total,
        "articles_with_scraped_at": total - missing,
        "earliest_scrape": mn,
        "latest_scrape": mx,
        "scrape_duration_days": duration_days,
    }
