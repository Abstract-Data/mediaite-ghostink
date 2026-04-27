"""Integration: cohort ``config_hash`` gate before compare / report paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forensics.analysis.orchestrator.comparison import _validate_compare_artifact_hashes
from forensics.config.settings import ForensicsSettings
from forensics.paths import AnalysisArtifactPaths
from forensics.utils.provenance import (
    compute_analysis_config_hash,
    validate_analysis_result_config_hashes,
)


def _minimal_paths(tmp: Path) -> AnalysisArtifactPaths:
    db = tmp / "articles.db"
    db.write_text("", encoding="utf-8")
    (tmp / "features").mkdir(parents=True, exist_ok=True)
    (tmp / "embeddings").mkdir(parents=True, exist_ok=True)
    analysis = tmp / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    return AnalysisArtifactPaths.from_layout(
        tmp,
        db,
        tmp / "features",
        tmp / "embeddings",
        analysis_dir=analysis,
    )


@pytest.mark.integration
def test_validate_analysis_result_config_hashes_rejects_stale_config_hash(
    tmp_path: Path,
) -> None:
    """Stale ``*_result.json`` must fail validation; fix = re-analyze or pin ``pipeline_b_mode``."""
    settings = ForensicsSettings()
    expected = compute_analysis_config_hash(settings)
    stale = "deadbeefcafebabe"
    assert stale != expected

    paths = _minimal_paths(tmp_path)
    slugs = ("fixture-target", "fixture-control")
    for slug in slugs:
        paths.result_json(slug).write_text(
            json.dumps({"config_hash": stale}),
            encoding="utf-8",
        )

    ok, msg = validate_analysis_result_config_hashes(
        settings,
        paths.analysis_dir,
        list(slugs),
    )
    assert ok is False
    assert "Analysis artifact compatibility failed" in msg
    assert "stale or mismatched analysis config hashes" in msg

    with pytest.raises(
        ValueError, match="config_hash|stale|mismatch|Analysis artifact compatibility"
    ):
        _validate_compare_artifact_hashes(list(slugs[0:1]), list(slugs[1:2]), paths, settings)
