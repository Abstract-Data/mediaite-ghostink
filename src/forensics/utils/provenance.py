"""Deterministic hashes and chain-of-custody helpers for forensic reporting."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Set
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from forensics.config.settings import ForensicsSettings
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import open_repository_connection

CUSTODY_FILENAME = "corpus_custody.json"


def compute_model_config_hash(
    config: BaseModel,
    *,
    length: int = 16,
    exclude: Set[str] | frozenset[str] | None = None,
    round_trip: bool = False,
) -> str:
    """SHA-256 prefix of a deterministic JSON serialization of ``config`` (RF-DRY-003)."""
    dump_kw: dict[str, Any] = {"mode": "json"}
    if exclude:
        dump_kw["exclude"] = set(exclude)
    if round_trip:
        dump_kw["round_trip"] = True
    payload = config.model_dump(**dump_kw)
    config_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(config_str.encode()).hexdigest()[:length]


def compute_config_hash(settings: ForensicsSettings) -> str:
    """Deterministic short hash of the pipeline configuration (excludes volatile ``db_path``)."""
    return compute_model_config_hash(
        settings,
        length=12,
        exclude=frozenset({"db_path"}),
    )


def compute_corpus_hash(db_path: Path) -> str:
    """Hash ordered ``content_hash`` values from the articles table."""
    if not db_path.is_file():
        return hashlib.sha256(b"").hexdigest()[:12]
    conn = open_repository_connection(db_path)
    try:
        hashes = conn.execute(
            "SELECT content_hash FROM articles ORDER BY id",
        ).fetchall()
    finally:
        conn.close()
    combined = "|".join(h[0] for h in hashes if h[0])
    return hashlib.sha256(combined.encode()).hexdigest()[:12]


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
    payload = {
        "corpus_hash": compute_corpus_hash(db_path),
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    path = analysis_dir / CUSTODY_FILENAME
    write_json_artifact(path, payload)
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


def audit_scrape_timestamps(db_path: Path) -> dict[str, Any]:
    """Summarize ``scraped_at`` coverage for chain-of-custody notebooks."""
    if not db_path.is_file():
        return {
            "articles_total": 0,
            "missing_scraped_at": 0,
            "duplicates_excluded": 0,
            "scraped_at_min": None,
            "scraped_at_max": None,
            "message": "database file not found",
        }
    conn = open_repository_connection(db_path)
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
            "message": "empty database",
        }
    return {
        "articles_total": int(row["n"] or 0),
        "missing_scraped_at": int(row["missing"] or 0),
        "duplicates_excluded": int(row["dups"] or 0),
        "scraped_at_min": bounds["mn"] if bounds else None,
        "scraped_at_max": bounds["mx"] if bounds else None,
    }
