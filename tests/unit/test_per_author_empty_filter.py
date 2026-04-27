"""Per-author empty feature filter must not widen to the full multi-author frame."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from forensics.analysis.orchestrator import per_author as pa_mod
from forensics.config import get_settings
from forensics.models.author import Author
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.parquet import write_parquet_atomic
from forensics.storage.repository import Repository, init_db


def test_run_per_author_analysis_returns_none_when_author_slice_empty(
    tmp_path: Path,
    forensics_config_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ = forensics_config_path
    db = tmp_path / "articles.db"
    init_db(db)
    author = Author(
        name="X",
        slug="slug-x",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 1, 1),
        archive_url="https://example.com/x",
    )
    rows = [
        {
            "author_id": "other",
            "timestamp": datetime(2022, 6, 1, tzinfo=UTC),
            "article_id": "a1",
            "word_count": 100,
            "ttr": 0.5,
        }
    ]
    feat = tmp_path / "features"
    feat.mkdir()
    pq_path = feat / "slug-x.parquet"
    write_parquet_atomic(pq_path, rows)

    paths = AnalysisArtifactPaths.from_layout(
        tmp_path,
        db,
        feat,
        tmp_path / "embeddings",
    )
    cfg = get_settings()

    with Repository(db) as repo:
        repo.upsert_author(author)
        with caplog.at_level("WARNING"):
            out = pa_mod._run_per_author_analysis(
                "slug-x",
                repo,
                paths,
                cfg,
                probability_trajectory_by_slug={},
                exploratory=True,
                allow_pre_phase16_embeddings=False,
            )
    assert out is None
    assert "per_author frame empty after filter" in caplog.text
