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

from forensics.config.analysis_settings import AnalysisConfig
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import CorpusCustody
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import open_repository_connection

CUSTODY_FILENAME = "corpus_custody.json"


def _build_recursive_hash_payload(model: BaseModel) -> dict[str, Any]:
    """Collect hash-flagged fields from nested ``BaseModel`` trees into one flat dict.

    Leaf keys match the legacy flat ``AnalysisConfig`` field names so
    ``compute_model_config_hash(settings.analysis)`` stays stable across the
    nested refactor (ADR-0xx).
    """
    out: dict[str, Any] = {}
    for name, info in model.__class__.model_fields.items():
        val = getattr(model, name)
        extra = info.json_schema_extra
        if isinstance(extra, dict) and extra.get("include_in_config_hash") is True:
            out[name] = val
        elif isinstance(val, BaseModel):
            out.update(_build_recursive_hash_payload(val))
    return out


def analysis_config_hash_field_names() -> frozenset[str]:
    """All leaf field names that participate in :func:`compute_model_config_hash` for analysis."""
    names: set[str] = set()

    def walk(model_cls: type[BaseModel]) -> None:
        for field_name, finfo in model_cls.model_fields.items():
            extra = finfo.json_schema_extra
            if isinstance(extra, dict) and extra.get("include_in_config_hash") is True:
                names.add(field_name)
            ann = finfo.annotation
            inner = _unwrap_nested_basemodel(ann)
            if inner is not None:
                walk(inner)

    walk(AnalysisConfig)
    return frozenset(names)


def _unwrap_nested_basemodel(annotation: Any) -> type[BaseModel] | None:
    """Resolve ``X``, ``X | None``, etc. to a ``BaseModel`` subclass when present."""
    from typing import get_args, get_origin

    origin = get_origin(annotation)
    if origin is not None:
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            inner = _unwrap_nested_basemodel(arg)
            if inner is not None:
                return inner
        return None
    try:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation
    except TypeError:
        return None
    return None


def _collect_hash_enumerated_fields(model: BaseModel) -> set[str] | None:
    """Return the set of field names on ``model`` flagged for inclusion in the hash.

    A field participates in the deterministic analysis config hash iff its
    pydantic ``json_schema_extra`` contains ``{"include_in_config_hash": True}``.
    Returns ``None`` when the model declares no such annotations — in that case
    the legacy behaviour (hash the whole ``model_dump``) applies.

    This enumeration approach (Phase 15 Step 0.4) makes it explicit which knobs
    are signal-bearing (must invalidate cached artifacts on change) versus
    ergonomic/performance-only (should NOT force recompute). See
    ``docs/settings_phase15.md`` for the per-field rationale.
    """
    included: set[str] = set()
    for name, info in model.__class__.model_fields.items():
        extra = info.json_schema_extra
        if isinstance(extra, dict) and extra.get("include_in_config_hash") is True:
            included.add(name)
    return included or None


def compute_model_config_hash(
    config: BaseModel,
    *,
    length: int = 16,
    exclude: Set[str] | frozenset[str] | None = None,
    round_trip: bool = False,
) -> str:
    """SHA-256 prefix of a deterministic JSON serialization of ``config`` (RF-DRY-003).

    If any field on ``config`` is annotated with
    ``json_schema_extra={"include_in_config_hash": True}``, only those fields
    participate in the hash (Phase 15 Step 0.4). Otherwise the full
    ``model_dump`` (minus anything in ``exclude``) is hashed — preserving the
    legacy behaviour for settings that have not been explicitly enumerated.
    """
    dump_kw: dict[str, Any] = {"mode": "json"}
    if exclude:
        dump_kw["exclude"] = set(exclude)
    if round_trip:
        dump_kw["round_trip"] = True

    if isinstance(config, AnalysisConfig):
        raw = _build_recursive_hash_payload(config)
        payload = json.loads(json.dumps(raw, default=str))
        config_str = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()[:length]

    enumerated = _collect_hash_enumerated_fields(config)
    if enumerated is not None:
        dump_kw["include"] = enumerated
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


def compute_analysis_config_hash(settings: ForensicsSettings) -> str:
    """Deterministic short hash for per-author analysis result compatibility."""
    return compute_model_config_hash(settings.analysis, length=16, round_trip=True)


def _scan_author_result_hashes(
    analysis_dir: Path,
    author_slugs: list[str],
    *,
    expected: str,
) -> tuple[list[str], list[str], list[str], list[tuple[str, str]]]:
    """Load per-slug results; return (missing, invalid, mismatched_messages, observed_hashes)."""
    missing: list[str] = []
    mismatched: list[str] = []
    invalid: list[str] = []
    observed_hashes: list[tuple[str, str]] = []
    for slug in author_slugs:
        path = analysis_dir / f"{slug}_result.json"
        if not path.is_file():
            missing.append(str(path))
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            invalid.append(str(path))
            continue
        actual = payload.get("config_hash")
        if isinstance(actual, str) and actual:
            observed_hashes.append((slug, actual))
        if actual != expected:
            mismatched.append(f"{path} config_hash={actual!r} expected={expected!r}")
    return missing, invalid, mismatched, observed_hashes


def validate_analysis_result_config_hashes(
    settings: ForensicsSettings,
    analysis_dir: Path,
    author_slugs: list[str],
) -> tuple[bool, str]:
    """Validate that per-author results match the current analysis config hash.

    P-01 — refuses a cohort where per-author ``*_result.json`` files carry
    **distinct** ``config_hash`` values (mixed pipeline runs), even before
    checking whether any hash matches the live settings.
    """
    expected = compute_analysis_config_hash(settings)
    missing, invalid, mismatched, observed_hashes = _scan_author_result_hashes(
        analysis_dir,
        author_slugs,
        expected=expected,
    )
    problems: list[str] = []
    if missing:
        problems.append("missing result artifacts: " + "; ".join(missing))
    if invalid:
        problems.append("invalid result artifacts: " + "; ".join(invalid))
    distinct = {h for _slug, h in observed_hashes}
    if len(distinct) > 1:
        detail = "; ".join(f"{s}={h!r}" for s, h in sorted(observed_hashes))
        problems.append(
            "mixed config_hash across authors (re-run full analysis for a single cohort): " + detail
        )
    elif mismatched:
        problems.append("stale or mismatched analysis config hashes: " + "; ".join(mismatched))
    if problems:
        return False, "Analysis artifact compatibility failed: " + " | ".join(problems)
    return True, "Analysis result config hashes match current analysis settings."


def _digest_content_hash_sequence(hashes: list[str | None]) -> str:
    """SHA-256 prefix of ``|``-joined non-empty ``content_hash`` values (order preserved)."""
    combined = "|".join(h for h in hashes if h)
    return hashlib.sha256(combined.encode()).hexdigest()[:12]


def compute_corpus_hash_legacy(db_path: Path) -> str:
    """Legacy corpus hash: all rows, ``ORDER BY id`` (insert / key order).

    .. deprecated::
        Prefer :func:`compute_corpus_hash` (analyzable corpus, content-hash order).
        Retained for ``corpus_custody`` schema v1 verification and ``corpus_hash_v1``.
    """
    if not db_path.is_file():
        return hashlib.sha256(b"").hexdigest()[:12]
    conn = open_repository_connection(db_path)
    try:
        hashes = conn.execute(
            "SELECT content_hash FROM articles ORDER BY id",
        ).fetchall()
    finally:
        conn.close()
    return _digest_content_hash_sequence([h[0] for h in hashes])


def compute_corpus_hash(db_path: Path) -> str:
    """Hash the analyzable corpus: non-duplicates only, ordered by ``content_hash``.

    Rows with ``is_duplicate != 0`` are excluded so the fingerprint matches the
    feature-extraction cohort rather than raw ingest order or surrogate key order.
    """
    if not db_path.is_file():
        return hashlib.sha256(b"").hexdigest()[:12]
    conn = open_repository_connection(db_path)
    try:
        hashes = conn.execute(
            "SELECT content_hash FROM articles WHERE is_duplicate = 0 ORDER BY content_hash",
        ).fetchall()
    finally:
        conn.close()
    return _digest_content_hash_sequence([h[0] for h in hashes])


def get_run_metadata(settings: ForensicsSettings) -> dict[str, str]:
    """Metadata dict for notebook headers and manifests."""
    import sys

    return {
        "config_hash": compute_config_hash(settings),
        "corpus_hash": compute_corpus_hash(settings.db_path),
        "timestamp": datetime.now(UTC).isoformat(),
        "python_version": sys.version,
    }


def read_latest_scraped_at_iso(db_path: Path) -> str | None:
    """D-09 — newest ``articles.scraped_at`` timestamp for run-metadata staleness cues."""
    if not db_path.is_file():
        return None
    conn = open_repository_connection(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(scraped_at) FROM articles WHERE scraped_at IS NOT NULL",
        ).fetchone()
    finally:
        conn.close()
    if not row or row[0] is None:
        return None
    return str(row[0])


def write_corpus_custody(db_path: Path, analysis_dir: Path) -> Path:
    """Record corpus hashes at end of analysis for ``report --verify``."""
    custody = CorpusCustody(
        schema_version=2,
        corpus_hash=compute_corpus_hash(db_path),
        corpus_hash_v1=compute_corpus_hash_legacy(db_path),
        recorded_at=datetime.now(UTC),
    )
    path = analysis_dir / CUSTODY_FILENAME
    write_json_artifact(path, custody)
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
    """Return (ok, message) comparing live corpus hash to custody file.

    Schema v1 (missing ``schema_version``): compare legacy id-ordered hash to
    ``corpus_hash`` (pre–Phase-16 on-disk layout). Schema v2: compare analyzable
    corpus hash from :func:`compute_corpus_hash` to ``corpus_hash``.
    """
    rec = load_corpus_custody(analysis_dir)
    if rec is None:
        return False, f"No custody record at {analysis_dir / CUSTODY_FILENAME}"
    raw_version = rec.get("schema_version")
    if raw_version is None:
        version = 1
    elif isinstance(raw_version, int):
        version = raw_version
    elif isinstance(raw_version, str) and raw_version.isdigit():
        version = int(raw_version)
    else:
        return False, f"Invalid corpus_custody schema_version: {raw_version!r}"

    if version == 1:
        current = compute_corpus_hash_legacy(db_path)
    elif version == 2:
        current = compute_corpus_hash(db_path)
    else:
        return False, f"Unknown corpus_custody schema_version: {version}"

    expected = rec.get("corpus_hash")
    if expected != current:
        return (
            False,
            f"Corpus hash mismatch: stored={expected!r} current={current!r} (schema v{version})",
        )
    return True, f"Corpus hash matches custody record (schema v{version})."


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
