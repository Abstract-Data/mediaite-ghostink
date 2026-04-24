"""Unit tests for ``compute_convergence_scores``.

Covers the public API in ``forensics.analysis.convergence``:

* empty-input guards,
* single change-point detection,
* multi-feature alignment inside the window,
* no-alignment when change points fall outside the window,
* graceful handling of ``total_feature_count=0`` / empty feature list,
* Phase 15 B2 family-based ratio + per-family max score,
* Phase 15 E1 DEBUG logging of component signals,
* Phase 15 J5 CP-source dispatch (raw vs section-adjusted).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from forensics.analysis.convergence import (
    FAMILY_COUNT,
    ConvergenceInput,
    compute_convergence_scores,
)
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint


def _cp(
    feature_name: str,
    timestamp: datetime,
    *,
    confidence: float = 0.9,
    effect_size: float = 0.8,
    direction: str = "increase",
    method: str = "pelt",
    author_id: str = "author-1",
) -> ChangePoint:
    return ChangePoint(
        feature_name=feature_name,
        author_id=author_id,
        timestamp=timestamp,
        confidence=confidence,
        method=method,  # type: ignore[arg-type]
        effect_size_cohens_d=effect_size,
        direction=direction,  # type: ignore[arg-type]
    )


def _settings_with(**analysis_overrides: object) -> ForensicsSettings:
    """Build a ``ForensicsSettings`` with ``AnalysisConfig`` overrides."""
    base = ForensicsSettings(authors=[])
    new_analysis = base.analysis.model_copy(update=analysis_overrides)
    return base.model_copy(update={"analysis": new_analysis})


def test_no_changepoints_returns_empty() -> None:
    """With no change points and no auxiliary signals, the result is empty."""
    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=[],
            centroid_velocities=[],
            baseline_similarity_curve=[],
            total_feature_count=5,
        )
    )
    assert result == []


def test_single_changepoint_single_feature_emits_window() -> None:
    """A lone strong CP still emits a window via the Pipeline-A >0.5 / B threshold path."""
    # Under Phase 15 B2, the ratio is len(families)/FAMILY_COUNT == 1/8 so the
    # ratio gate fails; the window survives only because the A-score (0.9*0.8)
    # clears 0.5 AND pipeline_b_score clears 0.5 via strong velocity+similarity
    # signals. That drives the regression fixture below.
    cp_time = datetime(2024, 3, 15, tzinfo=UTC)
    cps = [_cp("ttr", cp_time)]

    # Strong velocity peak + similarity drop so Pipeline B clears 0.5.
    velocities = [
        ("2024-01", 0.05),
        ("2024-02", 0.08),
        ("2024-03", 0.90),
        ("2024-04", 0.85),
    ]
    baseline = [
        (cp_time + timedelta(days=d), s)
        for d, s in [(0, 0.95), (10, 0.90), (20, 0.60), (30, 0.30), (40, 0.20)]
    ]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=velocities,
            baseline_similarity_curve=baseline,
            window_days=90,
            total_feature_count=1,
        )
    )

    assert len(result) >= 1
    window = result[0]
    assert window.start_date == cp_time.date()
    assert window.end_date == cp_time.date() + timedelta(days=90)
    assert window.features_converging == ["ttr"]
    # 1 family (lexical_richness) of 8 — ratio is now family-based.
    assert window.convergence_ratio == pytest.approx(1.0 / FAMILY_COUNT)


def test_multi_feature_alignment_within_window_detected() -> None:
    """Multiple families inside the window trigger convergence via the ratio gate."""
    base = datetime(2024, 6, 1, tzinfo=UTC)
    # One feature per distinct family so ratio = FAMILY_COUNT/FAMILY_COUNT = 1.0
    feature_names = [
        "ttr",  # lexical_richness
        "flesch_kincaid",  # readability
        "sent_length_mean",  # sentence_structure
        "paragraph_length_variance",  # paragraph_shape
        "bigram_entropy",  # entropy
        "self_similarity_30d",  # self_similarity
        "ai_marker_frequency",  # ai_markers
        "first_person_ratio",  # voice
    ]
    cps = [_cp(name, base + timedelta(days=i * 3)) for i, name in enumerate(feature_names)]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.6,
            total_feature_count=len(feature_names),
        )
    )

    assert result, "expected at least one convergence window"
    first = result[0]
    assert first.start_date == base.date()
    assert first.convergence_ratio == pytest.approx(1.0)
    assert sorted(first.features_converging) == sorted(feature_names)


def test_changepoints_outside_window_no_convergence() -> None:
    """Change points separated by more than ``window_days`` should not converge."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    cps = [
        _cp("ttr", base),
        _cp("flesch_kincaid", base + timedelta(days=200)),
        _cp("sent_length_mean", base + timedelta(days=400)),
        _cp("bigram_entropy", base + timedelta(days=600)),
        _cp("self_similarity_30d", base + timedelta(days=800)),
    ]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.6,
            total_feature_count=5,
        )
    )

    assert result == []


def test_empty_feature_total_returns_empty() -> None:
    """``total_feature_count=0`` must short-circuit without a ZeroDivisionError."""
    cp_time = datetime(2024, 2, 1, tzinfo=UTC)
    cps = [_cp("ttr", cp_time), _cp("mattr", cp_time + timedelta(days=2))]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            total_feature_count=0,
        )
    )

    assert result == []


def test_fully_empty_inputs_graceful() -> None:
    """All-empty inputs (no CPs, no velocities, no curve, zero total) do not crash."""
    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=[],
            centroid_velocities=[],
            baseline_similarity_curve=[],
            total_feature_count=0,
        )
    )
    assert result == []


def test_pipeline_a_family_score_one_vote_per_family() -> None:
    """Phase 15 B2: CPs across 3 families → ratio 3/8, score = mean of per-family maxes."""
    base = datetime(2024, 6, 1, tzinfo=UTC)
    # Three families, two with competing CPs so the per-family max wins.
    # lexical_richness: max(0.9*0.8, 0.4*0.3) = 0.72
    # readability:     max(0.8*0.5) = 0.40
    # ai_markers:      max(0.5*0.4, 0.6*0.2) = 0.20
    cps = [
        _cp("ttr", base, confidence=0.9, effect_size=0.8),
        _cp("hapax_ratio", base + timedelta(days=1), confidence=0.4, effect_size=0.3),
        _cp("flesch_kincaid", base + timedelta(days=2), confidence=0.8, effect_size=0.5),
        _cp("ai_marker_frequency", base + timedelta(days=3), confidence=0.5, effect_size=0.4),
        _cp("hedging_frequency", base + timedelta(days=4), confidence=0.6, effect_size=0.2),
    ]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=3 / FAMILY_COUNT - 0.01,  # let the ratio gate pass
            total_feature_count=len(cps),
        )
    )

    assert result, "expected one convergence window"
    window = result[0]
    assert window.convergence_ratio == pytest.approx(3 / FAMILY_COUNT)
    # Mean of per-family maxes: (0.72 + 0.40 + 0.20) / 3 = 0.44
    assert window.pipeline_a_score == pytest.approx((0.72 + 0.40 + 0.20) / 3.0)
    # Representative features: ttr (lex), flesch_kincaid (read), ai_marker_frequency (ai)
    assert set(window.features_converging) == {"ttr", "flesch_kincaid", "ai_marker_frequency"}


def test_convergence_debug_logging_emits(caplog: pytest.LogCaptureFixture) -> None:
    """Phase 15 E1: per-window component signals are DEBUG-logged."""
    caplog.set_level(logging.DEBUG, logger="forensics.analysis.convergence")
    base = datetime(2024, 6, 1, tzinfo=UTC)
    cps = [_cp("ttr", base), _cp("flesch_kincaid", base + timedelta(days=2))]

    compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[("2024-06", 0.5)],
            baseline_similarity_curve=[],
            window_days=30,
            total_feature_count=2,
        )
    )

    debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("peak_signal=" in m and "pipeline_b=" in m for m in debug_messages)
    assert any("author=author-1" in m for m in debug_messages)


def test_convergence_cp_source_dispatch(caplog: pytest.LogCaptureFixture) -> None:
    """Phase 15 J5: ``raw`` keeps PELT/BOCPD only; ``section_adjusted`` prefers *_section_adjusted.

    Unit 4 is what adds the ``pelt_section_adjusted`` / ``bocpd_section_adjusted``
    literals to ``ChangePoint.method``; until then the adjusted method names
    cannot be constructed via Pydantic. We exercise the dispatch filter
    directly here (``_filter_change_points_by_source``) to avoid that
    blocker, and pin two behaviours:

    1. ``"raw"`` drops any non-PELT/BOCPD methods (e.g. ``chow``).
    2. ``"section_adjusted"`` with no matching methods falls back to raw
       and logs at INFO.
    """
    from forensics.analysis.convergence import _filter_change_points_by_source

    # Direct filter semantics — raw keeps only pelt/bocpd.
    mixed = [
        _cp("ttr", datetime(2024, 1, 1, tzinfo=UTC), method="pelt"),
        _cp("flesch_kincaid", datetime(2024, 1, 2, tzinfo=UTC), method="bocpd"),
        _cp("sent_length_mean", datetime(2024, 1, 3, tzinfo=UTC), method="chow"),
    ]
    raw_only = _filter_change_points_by_source(mixed, "raw")
    assert {cp.method for cp in raw_only} == {"pelt", "bocpd"}

    # Fallback: section_adjusted with no matches → raw and INFO log.
    caplog.clear()
    caplog.set_level(logging.INFO, logger="forensics.analysis.convergence")
    fallback = _filter_change_points_by_source(mixed, "section_adjusted")
    assert {cp.method for cp in fallback} == {"pelt", "bocpd"}
    assert any(
        "falling back to raw" in r.message for r in caplog.records if r.levelno == logging.INFO
    )

    # End-to-end: using settings.convergence_cp_source="raw" on a mixed list
    # produces the same windows as explicitly filtering ahead of time.
    base = datetime(2024, 6, 1, tzinfo=UTC)
    feature_names = [
        "ttr",
        "flesch_kincaid",
        "sent_length_mean",
        "paragraph_length_variance",
        "bigram_entropy",
        "self_similarity_30d",
        "ai_marker_frequency",
        "first_person_ratio",
    ]
    raw_cps = [_cp(n, base + timedelta(days=i), method="pelt") for i, n in enumerate(feature_names)]
    noise = [_cp("ttr", base + timedelta(days=200), method="chow")]

    settings_raw = _settings_with(convergence_cp_source="raw")
    result_raw = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=raw_cps + noise,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.6,
            total_feature_count=len(feature_names),
            settings=settings_raw,
        )
    )
    assert result_raw, "raw dispatch should emit a window from the pelt CPs"
    # The Jan-1 noise chow CP must NOT seed a separate window under raw.
    window_starts = {w.start_date for w in result_raw}
    assert (base + timedelta(days=200)).date() not in window_starts


def test_percentile_pipeline_b_mode_lifts_peak_signal() -> None:
    """Phase 15 E3: percentile mode produces a peak_signal > 0 where legacy z-score floors.

    Compare the two modes on identical inputs: a velocity sequence with a
    clear ramp. Legacy z-score caps at ``(max - mean) / (2 σ)`` which is
    ≈ 0.43 for the ramp; percentile mode lifts to 1.0 because the window
    contains the author's historical max.
    """
    cp_time = datetime(2024, 3, 15, tzinfo=UTC)
    cps = [_cp("ttr", cp_time)]
    velocities = [(f"2024-{m:02d}", 0.1 * m) for m in range(1, 7)]

    def _score(mode: str) -> float:
        settings = _settings_with(pipeline_b_mode=mode)
        windows = compute_convergence_scores(
            ConvergenceInput.build(
                change_points=cps,
                centroid_velocities=velocities,
                baseline_similarity_curve=[],
                ai_convergence_curve=[("2024-03", 0.1), ("2024-06", 0.9)],
                window_days=90,
                total_feature_count=1,
                settings=settings,
            )
        )
        assert windows, f"{mode} mode should yield a window for this fixture"
        return windows[0].pipeline_b_score

    legacy_score = _score("legacy")
    percentile_score = _score("percentile")
    assert percentile_score > legacy_score, (
        f"percentile={percentile_score} should exceed legacy={legacy_score}"
    )
