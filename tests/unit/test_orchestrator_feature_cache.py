"""Feature-series cache inside ``_run_hypothesis_tests_for_changepoints`` (Phase 15 F2).

Verifies that per-feature median-imputation is executed at most once per
unique feature name within a single author run, that caches don't leak
between invocations (i.e. per-author isolation), and that CPs on columns
missing from the frame are skipped cleanly without populating the cache.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl

from forensics.analysis import orchestrator as orch
from forensics.config.settings import AnalysisConfig
from forensics.models.analysis import ChangePoint


def _timestamps(n: int) -> list[datetime]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [base + timedelta(days=i) for i in range(n)]


def _cp(feature: str, ts: datetime) -> ChangePoint:
    return ChangePoint(
        feature_name=feature,
        author_id="author-1",
        timestamp=ts,
        confidence=0.9,
        method="pelt",
        effect_size_cohens_d=0.4,
        direction="increase",
    )


def _frame(feature_names: list[str], n_rows: int = 12) -> pl.DataFrame:
    # Non-constant series so bootstrap / Welch don't degenerate; signed shift
    # so hypothesis tests actually run without short-circuiting on std==0.
    import numpy as np

    rng = np.random.default_rng(42)
    data: dict[str, list[float]] = {}
    for fname in feature_names:
        pre = rng.normal(0.0, 0.1, size=n_rows // 2).tolist()
        post = rng.normal(1.0, 0.1, size=n_rows - n_rows // 2).tolist()
        data[fname] = pre + post
    return pl.DataFrame(data)


def _cfg() -> AnalysisConfig:
    # Tight bootstrap for test speed; behaviour of the cache is independent
    # of bootstrap count.
    return AnalysisConfig(
        bootstrap_iterations=25,
        significance_threshold=0.05,
        effect_size_threshold=0.2,
        fdr_grouping="author",  # avoid feature_families dependency in unit tests
    )


def test_cache_reused_across_cps_same_feature(monkeypatch) -> None:
    """Same feature across multiple CPs => ``_clean_feature_series`` called once."""
    calls: list[str] = []
    real = orch._clean_feature_series

    def _counting(df: pl.DataFrame, feature_name: str) -> list[float]:
        calls.append(feature_name)
        return real(df, feature_name)

    monkeypatch.setattr(orch, "_clean_feature_series", _counting)

    df = _frame(["feat_A", "feat_B"], n_rows=12)
    ts = _timestamps(12)
    mid = ts[6]
    change_points = [
        _cp("feat_A", mid),
        _cp("feat_A", mid),  # same feature — must hit the cache
        _cp("feat_B", mid),
        _cp("feat_A", mid),  # still cached from the first lookup
    ]
    orch._run_hypothesis_tests_for_changepoints(
        df,
        ts,
        change_points,
        author_id="author-1",
        analysis_cfg=_cfg(),
    )
    assert calls == ["feat_A", "feat_B"], f"expected one clean per unique feature, got {calls}"


def test_cache_isolated_per_author(monkeypatch) -> None:
    """The cache lives in function-local scope; two invocations share no state."""
    calls: list[str] = []
    real = orch._clean_feature_series

    def _counting(df: pl.DataFrame, feature_name: str) -> list[float]:
        calls.append(feature_name)
        return real(df, feature_name)

    monkeypatch.setattr(orch, "_clean_feature_series", _counting)

    df1 = _frame(["shared_feat"], n_rows=12)
    df2 = _frame(["shared_feat"], n_rows=12)
    ts = _timestamps(12)
    cps = [_cp("shared_feat", ts[6])]

    orch._run_hypothesis_tests_for_changepoints(df1, ts, cps, author_id="A", analysis_cfg=_cfg())
    orch._run_hypothesis_tests_for_changepoints(df2, ts, cps, author_id="B", analysis_cfg=_cfg())
    # One call per invocation — the second author cannot pick up author A's
    # cleaned series because the cache is local to each call.
    assert calls == ["shared_feat", "shared_feat"], calls


def test_cache_handles_missing_feature_column(monkeypatch) -> None:
    """CPs on absent columns are skipped; no clean call, no cache pollution."""
    calls: list[str] = []
    real = orch._clean_feature_series

    def _counting(df: pl.DataFrame, feature_name: str) -> list[float]:
        calls.append(feature_name)
        return real(df, feature_name)

    monkeypatch.setattr(orch, "_clean_feature_series", _counting)

    df = _frame(["present_feat"], n_rows=12)
    ts = _timestamps(12)
    cps = [
        _cp("present_feat", ts[6]),
        _cp("ghost_feat", ts[6]),  # not in df.columns — must be skipped
        _cp("present_feat", ts[6]),  # still cached
    ]
    out = orch._run_hypothesis_tests_for_changepoints(
        df, ts, cps, author_id="author-1", analysis_cfg=_cfg()
    )
    assert calls == ["present_feat"], calls
    # The returned tests list is shape-agnostic here — we care that the run
    # completes without raising and that the cache bookkeeping matches. The
    # tests themselves are validated in ``test_statistics.py``.
    assert isinstance(out, list)
