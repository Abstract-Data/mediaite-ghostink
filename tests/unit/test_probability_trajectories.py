"""Tests for :mod:`forensics.analysis.probability_trajectories` (Pipeline C inputs)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from forensics.analysis.convergence import compute_probability_pipeline_score
from forensics.analysis.probability_trajectories import build_probability_trajectory_by_slug
from forensics.config import get_settings
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.parquet import write_parquet_atomic


def _paths(tmp: Path) -> AnalysisArtifactPaths:
    db = tmp / "articles.db"
    db.write_text("", encoding="utf-8")
    feat = tmp / "features"
    feat.mkdir(parents=True, exist_ok=True)
    emb = tmp / "embeddings"
    emb.mkdir(parents=True, exist_ok=True)
    ana = tmp / "analysis"
    ana.mkdir(parents=True, exist_ok=True)
    return AnalysisArtifactPaths.from_layout(tmp, db, feat, emb, analysis_dir=ana)


def test_build_from_probability_shard(tmp_path: Path) -> None:
    """``data/probability/<slug>.parquet`` rows aggregate to monthly trajectories."""
    prob_dir = tmp_path / "data" / "probability"
    prob_dir.mkdir(parents=True)
    rows = [
        {
            "article_id": "a1",
            "author_id": "1",
            "publish_date": date(2024, 1, 15),
            "mean_perplexity": 50.0,
            "perplexity_variance": 10.0,
            "binoculars_score": None,
        },
        {
            "article_id": "a2",
            "author_id": "1",
            "publish_date": date(2024, 1, 20),
            "mean_perplexity": 52.0,
            "perplexity_variance": 12.0,
            "binoculars_score": None,
        },
        {
            "article_id": "a3",
            "author_id": "1",
            "publish_date": date(2024, 2, 10),
            "mean_perplexity": 20.0,
            "perplexity_variance": 2.0,
            "binoculars_score": 0.5,
        },
    ]
    pl.DataFrame(rows).write_parquet(prob_dir / "author-one.parquet")

    paths = _paths(tmp_path)
    m = build_probability_trajectory_by_slug(paths, ["author-one", "missing"])
    assert list(m.keys()) == ["author-one"]
    traj = m["author-one"]
    assert traj.monthly_perplexity == [
        ("2024-01", pytest.approx(51.0)),
        ("2024-02", pytest.approx(20.0)),
    ]
    assert traj.monthly_burstiness[0][0] == "2024-01"
    assert traj.monthly_binoculars is not None
    assert len(traj.monthly_binoculars) == 1
    assert traj.monthly_binoculars[0][0] == "2024-02"
    assert traj.monthly_binoculars[0][1] == pytest.approx(0.5)


def test_feature_parquet_takes_precedence_when_columns_present(tmp_path: Path) -> None:
    """Per-author feature parquet is preferred when it already carries probability columns."""
    paths = _paths(tmp_path)
    prob_dir = tmp_path / "data" / "probability"
    prob_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "article_id": "p1",
                "author_id": "1",
                "publish_date": date(2024, 1, 10),
                "mean_perplexity": 1.0,
                "perplexity_variance": 1.0,
            },
        ]
    ).write_parquet(prob_dir / "dup.parquet")

    feat_rows = [
        {
            "article_id": "f1",
            "author_id": "1",
            "timestamp": datetime(2024, 1, 5, tzinfo=UTC),
            "mean_perplexity": 80.0,
            "perplexity_variance": 30.0,
        },
    ]
    write_parquet_atomic(paths.features_parquet("dup"), feat_rows)

    m = build_probability_trajectory_by_slug(paths, ["dup"])
    assert m["dup"].monthly_perplexity[0][1] == pytest.approx(80.0)


def test_pipeline_c_score_nonzero_when_trajectory_loaded(tmp_path: Path) -> None:
    """End-to-end from shard file to a positive Pipeline C score for a spanning window."""
    prob_dir = tmp_path / "data" / "probability"
    prob_dir.mkdir(parents=True)
    rows = [
        {
            "article_id": "a1",
            "author_id": "1",
            "publish_date": date(2024, 1, 5),
            "mean_perplexity": 100.0,
            "perplexity_variance": 40.0,
        },
        {
            "article_id": "a2",
            "author_id": "1",
            "publish_date": date(2024, 2, 5),
            "mean_perplexity": 15.0,
            "perplexity_variance": 3.0,
        },
    ]
    pl.DataFrame(rows).write_parquet(prob_dir / "score-author.parquet")
    paths = _paths(tmp_path)
    traj = build_probability_trajectory_by_slug(paths, ["score-author"])["score-author"]
    settings = get_settings()
    score = compute_probability_pipeline_score(
        date(2024, 1, 1),
        date(2024, 2, 29),
        traj,
        settings=settings,
    )
    assert score > 0.0
