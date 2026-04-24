"""Tests for :func:`compute_author_drift_pipeline` (synthetic embeddings, mocked UMAP)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import numpy as np

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.drift import (
    ArticleEmbedding,
    compute_author_drift_pipeline,
    load_ai_baseline_embeddings,
)
from forensics.config.settings import (
    AnalysisConfig,
    ForensicsSettings,
    ReportConfig,
    ScrapingConfig,
)
from forensics.storage.repository import init_db


def _settings() -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(baseline_embedding_count=3, intra_variance_pairwise_max=10),
        report=ReportConfig(),
    )


def _paths(tmp_path: Path) -> AnalysisArtifactPaths:
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    return AnalysisArtifactPaths.from_layout(
        tmp_path,
        db_path,
        tmp_path / "data" / "features",
        tmp_path / "data" / "embeddings",
    )


def test_compute_author_drift_pipeline_writes_artifacts(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    slug = "drift-pipe-author"
    author_id = "author-drift-1"

    embs: list[ArticleEmbedding] = []
    jan = datetime(2024, 1, 5, tzinfo=UTC)
    feb = datetime(2024, 2, 5, tzinfo=UTC)
    for i in range(3):
        ts = jan + timedelta(days=i)
        vec = np.array([1.0, 0.0, 0.0, float(i) * 0.05], dtype=np.float32)
        embs.append(ArticleEmbedding(published_at=ts, embedding=vec))
    for i in range(3):
        ts = feb + timedelta(days=i)
        vec = np.array([0.0, 1.0, 0.0, float(i) * 0.05], dtype=np.float32)
        embs.append(ArticleEmbedding(published_at=ts, embedding=vec))

    fake_umap = {"projections": {slug: []}, "ai_projection": None}
    with mock.patch(
        "forensics.analysis.drift.generate_umap_projection",
        return_value=fake_umap,
    ):
        res = compute_author_drift_pipeline(
            slug,
            author_id,
            embs,
            _settings(),
            paths=paths,
        )
    assert res is not None
    assert res.drift_scores.author_id == author_id
    assert res.drift_scores.ai_baseline_similarity is None
    assert paths.drift_json(slug).is_file()
    assert paths.centroids_npz(slug).is_file()


def test_nested_generated_ai_baseline_populates_similarity(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    slug = "drift-pipe-author"
    author_id = "author-drift-1"
    cell_dir = paths.ai_baseline_dir(slug) / "llama3.1-8b" / "raw_t0.0" / "embeddings"
    cell_dir.mkdir(parents=True)
    (paths.ai_baseline_dir(slug) / "generation_manifest.json").write_text(
        '{"author_slug": "drift-pipe-author", "models": []}',
        encoding="utf-8",
    )
    np.save(cell_dir / "good.npy", np.ones(384, dtype=np.float32))
    np.save(cell_dir / "bad.npy", np.ones(12, dtype=np.float32))

    loaded = load_ai_baseline_embeddings(slug, paths)
    assert len(loaded) == 1
    assert loaded[0].shape == (384,)

    jan = datetime(2024, 1, 5, tzinfo=UTC)
    feb = datetime(2024, 2, 5, tzinfo=UTC)
    embs = [
        ArticleEmbedding(published_at=jan, embedding=np.ones(384, dtype=np.float32)),
        ArticleEmbedding(published_at=feb, embedding=np.ones(384, dtype=np.float32) * 0.9),
    ]

    with mock.patch(
        "forensics.analysis.drift.generate_umap_projection",
        return_value={"projections": {slug: []}, "ai_projection": None},
    ):
        res = compute_author_drift_pipeline(
            slug,
            author_id,
            embs,
            _settings(),
            paths=paths,
        )
    assert res is not None
    assert res.drift_scores.ai_baseline_similarity is not None
