"""Staleness and run-metadata helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.json_io import write_json_artifact
from forensics.utils.provenance import compute_model_config_hash


def _author_result_current(
    paths: AnalysisArtifactPaths, config: ForensicsSettings, slug: str
) -> bool:
    path = paths.result_json(slug)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    expected = compute_model_config_hash(config.analysis, length=16, round_trip=True)
    return payload.get("config_hash") == expected


def _stale_author_slugs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    author_slug: str | None,
) -> list[str]:
    if author_slug is not None:
        return [author_slug]
    configured = [author.slug for author in config.authors]
    if all(_author_result_current(paths, config, slug) for slug in configured):
        return []
    # Hypothesis-test correction is global across authors, so a mixed current/stale
    # cohort must be recomputed together to avoid FDR denominator drift.
    return configured


def _merge_run_metadata(
    paths: AnalysisArtifactPaths,
    results: dict[str, AnalysisResult],
    comparison_payload: dict[str, Any],
    *,
    last_scraped_at: str | None = None,
    section_residualized_sensitivity: dict[str, Any] | None = None,
) -> None:
    """Merge analysis run fields into ``run_metadata.json`` with a single read/write pair."""
    meta_path = paths.run_metadata_json()
    if meta_path.is_file():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    else:
        prev = {}
    # Phase 15 H2 — sort top-level lists for parallel/serial byte-identity.
    prev.update(
        {
            "full_analysis_authors": sorted(results.keys()),
            "authors_in_run": sorted(results.keys()),
            "comparison_targets": sorted(comparison_payload["targets"].keys()),
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    if last_scraped_at:
        prev["last_scraped_at"] = last_scraped_at
    if section_residualized_sensitivity:
        prev["section_residualized_sensitivity"] = section_residualized_sensitivity
    write_json_artifact(meta_path, prev)
