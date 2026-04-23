"""Unit tests for :func:`forensics.analysis.drift.load_drift_summary`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.drift import DriftSummary, load_drift_summary
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig
from forensics.models.analysis import DriftScores
from forensics.models.features import EmbeddingRecord
from forensics.storage.parquet import write_embeddings_manifest
from forensics.storage.repository import Repository, init_db


def _make_settings() -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(baseline_embedding_count=3),
    )


def _make_paths(tmp_path: Path) -> AnalysisArtifactPaths:
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    return AnalysisArtifactPaths.from_layout(
        tmp_path,
        db_path,
        tmp_path / "data" / "features",
        tmp_path / "data" / "embeddings",
    )


def test_load_drift_summary_prefers_cached_artifacts(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    slug = "cached-author"

    scores = DriftScores(
        author_id="author-id",
        baseline_centroid_similarity=0.9,
        ai_baseline_similarity=0.4,
        monthly_centroid_velocities=[0.1, 0.2],
        intra_period_variance_trend=[0.0, 0.01],
    )
    paths.drift_json(slug).write_text(scores.model_dump_json(), encoding="utf-8")
    np.savez_compressed(
        paths.centroids_npz(slug),
        months=np.array(["2024-01", "2024-02", "2024-03"], dtype="U7"),
        centroids=np.zeros((3, 4), dtype=np.float32),
    )
    curve = [
        {"published_at": "2024-01-01T00:00:00+00:00", "similarity": 1.0},
        {"published_at": "2024-01-15T00:00:00+00:00", "similarity": 0.95},
    ]
    paths.baseline_curve_json(slug).write_text(json.dumps(curve), encoding="utf-8")

    summary = load_drift_summary(slug, paths, settings=_make_settings())

    assert isinstance(summary, DriftSummary)
    assert summary.velocities == [("2024-02", 0.1), ("2024-03", 0.2)]
    assert len(summary.baseline_curve) == 2
    assert summary.baseline_curve[0][0] == datetime(2024, 1, 1, tzinfo=UTC)
    assert summary.baseline_curve[0][1] == 1.0


def test_load_drift_summary_fallback_labels_when_centroids_missing(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    slug = "no-centroids"

    scores = DriftScores(
        author_id="author-id",
        baseline_centroid_similarity=0.0,
        ai_baseline_similarity=0.0,
        monthly_centroid_velocities=[0.3, 0.4],
        intra_period_variance_trend=[0.0, 0.0],
    )
    paths.drift_json(slug).write_text(scores.model_dump_json(), encoding="utf-8")
    paths.baseline_curve_json(slug).write_text("[]", encoding="utf-8")

    summary = load_drift_summary(slug, paths, settings=_make_settings())

    assert summary.velocities == [("m0", 0.3), ("m1", 0.4)]
    assert summary.baseline_curve == []


def test_load_drift_summary_recomputes_from_embeddings(tmp_path: Path, sample_author) -> None:
    paths = _make_paths(tmp_path)
    with Repository(paths.db_path) as repo:
        repo.upsert_author(sample_author)

    slug_dir = paths.embeddings_dir / sample_author.slug
    slug_dir.mkdir(parents=True)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    records: list[EmbeddingRecord] = []
    for i in range(6):
        vec = np.array([1.0, 0.0, 0.0, float(i) * 0.1], dtype=np.float32)
        npy_path = slug_dir / f"art-{i}.npy"
        np.save(npy_path, vec)
        records.append(
            EmbeddingRecord(
                article_id=f"art-{i}",
                author_id=sample_author.id,
                timestamp=base + timedelta(days=i * 20),
                model_name="m",
                model_version="v",
                embedding_path=f"data/embeddings/{sample_author.slug}/art-{i}.npy",
                embedding_dim=4,
            )
        )
    write_embeddings_manifest(records, paths.embeddings_dir / "manifest.jsonl")

    summary = load_drift_summary(sample_author.slug, paths, settings=_make_settings())

    assert summary.velocities, "expected at least one month-to-month velocity"
    for month, vel in summary.velocities:
        assert isinstance(month, str)
        assert isinstance(vel, float)
    assert len(summary.baseline_curve) == len(records)
    for ts, sim in summary.baseline_curve:
        assert isinstance(ts, datetime)
        assert isinstance(sim, float)


def test_load_drift_summary_empty_when_no_data(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    summary = load_drift_summary("missing-slug", paths, settings=_make_settings())
    assert summary == DriftSummary(velocities=[], baseline_curve=[])
