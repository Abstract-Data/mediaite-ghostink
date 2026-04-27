"""T-02 — PELT/BOCPD determinism with duplicate timestamps (stable row order)."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import polars as pl

from forensics.analysis.changepoint import analyze_author_feature_changepoints
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig
from forensics.models.analysis import ChangePoint


def _settings_both_methods() -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(
            changepoint_methods=["pelt", "bocpd"],
            feature_workers=1,
            section_residualize_features=False,
        ),
    )


def _mean_shift_frame(*, n: int, ts: datetime) -> pl.DataFrame:
    rng = np.random.default_rng(2027)
    before = rng.normal(0.25, 0.04, n // 2)
    after = rng.normal(0.65, 0.04, n - n // 2)
    ttr = np.concatenate([before, after])
    rows = [{"article_id": f"art-{i:04d}", "timestamp": ts, "ttr": float(ttr[i])} for i in range(n)]
    return pl.DataFrame(rows)


def _serialize(cps: list[ChangePoint]) -> list[dict[object, object]]:
    return [c.model_dump(mode="json") for c in cps]


def test_changepoints_identical_for_same_sorted_frame_two_runs() -> None:
    ts = datetime(2018, 3, 1, 9, 0, tzinfo=UTC)
    df = _mean_shift_frame(n=48, ts=ts).sort(["timestamp", "article_id"])
    settings = _settings_both_methods()
    first = analyze_author_feature_changepoints(df, author_id="author-x", settings=settings)
    second = analyze_author_feature_changepoints(df, author_id="author-x", settings=settings)
    assert _serialize(first) == _serialize(second)


def test_changepoints_invariant_to_row_shuffle_when_resorted_like_parquet_loader() -> None:
    """Duplicate timestamps: canonical ``sort(["timestamp", "article_id"])`` must pin order."""
    ts = datetime(2015, 11, 11, 15, 30, tzinfo=UTC)
    base = _mean_shift_frame(n=44, ts=ts)
    canonical = base.sort(["timestamp", "article_id"])
    shuffled_a = base.sample(fraction=1.0, shuffle=True, seed=3)
    shuffled_b = base.sample(fraction=1.0, shuffle=True, seed=11)
    assert shuffled_a.sort(["timestamp", "article_id"]).equals(canonical)
    assert shuffled_b.sort(["timestamp", "article_id"]).equals(canonical)

    settings = _settings_both_methods()
    out_canon = analyze_author_feature_changepoints(
        canonical, author_id="author-z", settings=settings
    )
    out_a = analyze_author_feature_changepoints(
        shuffled_a.sort(["timestamp", "article_id"]),
        author_id="author-z",
        settings=settings,
    )
    out_b = analyze_author_feature_changepoints(
        shuffled_b.sort(["timestamp", "article_id"]),
        author_id="author-z",
        settings=settings,
    )
    assert _serialize(out_canon) == _serialize(out_a) == _serialize(out_b)
