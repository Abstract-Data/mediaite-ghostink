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
    PIPELINE_SCORE_PASS_THRESHOLD,
    ConvergenceInput,
    compute_convergence_scores,
)
from forensics.config.analysis_settings import apply_flat_analysis_overrides
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
    new_analysis = apply_flat_analysis_overrides(base.analysis, **analysis_overrides)
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
    """A lone strong CP still emits a window via the Pipeline-A >0.3 / B threshold path."""
    # Under Phase 15 B2 (post-issue-#5 regroup, FAMILY_COUNT == 6) the ratio
    # is len(families)/FAMILY_COUNT == 1/6 so the ratio gate fails; the
    # window survives only because the A-score (0.9*0.8) clears the AB
    # threshold (Fix-F lowered it to 0.3) AND pipeline_b_score also clears
    # it via strong velocity+similarity signals. That drives the regression
    # fixture below.
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
    # Phase 15 B-followup (issue #5): post-regroup the registry has 6
    # families (voice/paragraph_shape were folded). Picking one
    # representative per family covers them all.
    feature_names = [
        "ttr",  # lexical_richness
        "flesch_kincaid",  # readability
        "sent_length_mean",  # sentence_structure (now incl. paragraph_length_variance)
        "bigram_entropy",  # entropy
        "self_similarity_30d",  # self_similarity
        "ai_marker_frequency",  # ai_markers (now incl. first_person_ratio)
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


def test_ratio_pass_does_not_require_pipeline_b_signal() -> None:
    """Ratio gate can admit a window with ``pipeline_b_score == 0``.

    Phase 15 B2 uses *family* coverage (``len(families_hit) / FAMILY_COUNT``), so
    three lexical features (one family) cannot reach ``min_feature_ratio=0.75``.
    Use five distinct families so ``5 / FAMILY_COUNT >= 0.75`` while keeping
    velocity and baseline empty so Pipeline B stays zeroed.
    """
    base = datetime(2024, 1, 1, tzinfo=UTC)
    feature_names = [
        "ttr",  # lexical_richness
        "flesch_kincaid",  # readability
        "sent_length_mean",  # sentence_structure
        "bigram_entropy",  # entropy
        "self_similarity_30d",  # self_similarity
    ]
    cps = [_cp(name, base) for name in feature_names]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.75,
            total_feature_count=len(feature_names),
        )
    )

    assert len(result) == 1
    assert result[0].convergence_ratio == pytest.approx(5.0 / float(FAMILY_COUNT))
    assert result[0].pipeline_b_score == pytest.approx(0.0)


def test_ab_pass_can_emit_when_ratio_fails() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=[_cp("ttr", base, effect_size=0.8)],
            centroid_velocities=[("2024-01", 0.0), ("2024-02", 1.0), ("2024-03", 1.0)],
            baseline_similarity_curve=[
                (base, 0.9),
                (base + timedelta(days=60), 0.1),
            ],
            window_days=90,
            min_feature_ratio=0.75,
            total_feature_count=4,
        )
    )

    assert len(result) == 1
    assert result[0].convergence_ratio == pytest.approx(1.0 / float(FAMILY_COUNT))
    assert result[0].pipeline_a_score > 0.5
    assert result[0].pipeline_b_score > 0.5


def test_low_ratio_without_ab_pass_fails() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=[_cp("ttr", base, effect_size=0.8)],
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=90,
            min_feature_ratio=0.75,
            total_feature_count=4,
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

    Pins:

    1. ``"raw"`` drops any non-PELT/BOCPD methods (e.g. ``chow``).
    2. ``"section_adjusted"`` with no matching methods falls back to raw and
       logs at INFO when residualization was on (real signal: none survived).
    3. The same fallback logs at DEBUG when residualization is off (silent
       expected path: the producer wasn't configured to emit them).
    4. ``"section_adjusted"`` keeps the adjusted CPs untouched when present.
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

    # Fallback when residualization was *expected* — INFO log surfaces the gap.
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="forensics.analysis.convergence")
    fallback_expected = _filter_change_points_by_source(
        mixed, "section_adjusted", residualization_enabled=True
    )
    assert {cp.method for cp in fallback_expected} == {"pelt", "bocpd"}
    assert any(
        r.levelno == logging.INFO and "falling back to raw" in r.message for r in caplog.records
    )

    # Fallback when residualization was *off* — DEBUG only; default-config noise gone.
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="forensics.analysis.convergence")
    fallback_off = _filter_change_points_by_source(
        mixed, "section_adjusted", residualization_enabled=False
    )
    assert {cp.method for cp in fallback_off} == {"pelt", "bocpd"}
    assert not any(
        r.levelno >= logging.INFO and "falling back to raw" in r.message for r in caplog.records
    )
    assert any(
        r.levelno == logging.DEBUG and "falling back to raw" in r.message for r in caplog.records
    )

    # When adjusted CPs are present, they are returned and no fallback log fires.
    adjusted_mix = [
        _cp("ttr", datetime(2024, 1, 4, tzinfo=UTC), method="pelt_section_adjusted"),
        _cp("flesch_kincaid", datetime(2024, 1, 5, tzinfo=UTC), method="bocpd_section_adjusted"),
        _cp("sent_length_mean", datetime(2024, 1, 6, tzinfo=UTC), method="pelt"),
    ]
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="forensics.analysis.convergence")
    kept = _filter_change_points_by_source(adjusted_mix, "section_adjusted")
    assert {cp.method for cp in kept} == {"pelt_section_adjusted", "bocpd_section_adjusted"}
    assert not any("falling back to raw" in r.message for r in caplog.records)

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


def test_ab_threshold_persists_pb_positive_windows() -> None:
    """Fix-F: the AB-pass threshold (lowered 0.5 → 0.3) lets pb-positive windows survive.

    Constructs a single-family CP whose Pipeline-A score is ~0.42 (= 0.7 * 0.6)
    and a velocity ramp whose peak_signal alone yields ``pipeline_b_score`` ≈ 0.5
    in percentile mode (peak_signal=1.0, sim_signal=0, ai_signal=0 → mean = 0.5
    over [peak, sim]; ai-curve contribution makes it 0.4-0.5). The ratio gate
    fails (1 family / FAMILY_COUNT < 0.5), so the window can only persist via
    the AB threshold path. At the legacy 0.5 cutoff both pa and pb would be
    too low; at the Fix-F 0.3 cutoff both clear.
    """
    # Sanity-pin the constant so a future "raise the threshold back to 0.5"
    # change without context fails this test loudly.
    assert PIPELINE_SCORE_PASS_THRESHOLD == 0.3, (
        "Fix-F lowered the AB-pass threshold from 0.5 to 0.3; do not raise it "
        "again without re-validating the per-author pipeline_b_max distribution."
    )

    cp_time = datetime(2024, 3, 15, tzinfo=UTC)
    # confidence * effect_size = 0.7 * 0.6 = 0.42 → pa ~ 0.42 (above 0.3, below 0.5).
    cps = [_cp("ttr", cp_time, confidence=0.7, effect_size=0.6)]
    # Velocity ramp where the in-window months hit the historical max → percentile
    # mode peak_signal == 1.0; combined with sim/ai zeros, pb ≈ 0.5 (mean of [1, 0]).
    velocities = [(f"2024-{m:02d}", 0.1 * m) for m in range(1, 7)]

    settings = _settings_with(pipeline_b_mode="percentile")
    windows = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=velocities,
            baseline_similarity_curve=[],
            window_days=90,
            min_feature_ratio=0.99,  # ratio gate cannot save this single-family window
            total_feature_count=1,
            settings=settings,
        )
    )

    assert windows, "Fix-F: pb-positive single-family window should persist via the AB path"
    window = windows[0]
    assert window.pipeline_a_score > PIPELINE_SCORE_PASS_THRESHOLD
    assert window.pipeline_a_score < 0.5, (
        "pa should be < 0.5 so this window would have been filtered pre-Fix-F"
    )
    assert window.pipeline_b_score > PIPELINE_SCORE_PASS_THRESHOLD


def _drift_only_inputs() -> tuple[list[ChangePoint], list[tuple[str, float]]]:
    """Build a fixture where pa is tiny but pb_score clears the drift threshold.

    A single weak CP (confidence * effect_size = 0.1 * 0.1 = 0.01) keeps
    pipeline_a_score ≈ 0.01 — well below the 0.3 AB threshold — and the
    1-of-FAMILY_COUNT family ratio cannot clear ``min_feature_ratio = 0.5``.
    The velocity ramp gives ``peak_signal == 1.0`` in percentile mode so
    ``pipeline_b_score`` lands at ~0.5 (mean of [1.0, 0.0]) — above the
    0.3 drift-only threshold.
    """
    cp_time = datetime(2024, 3, 15, tzinfo=UTC)
    cps = [_cp("ttr", cp_time, confidence=0.1, effect_size=0.1)]
    velocities = [(f"2024-{m:02d}", 0.1 * m) for m in range(1, 7)]
    return cps, velocities


def test_drift_only_window_persists_when_pa_is_low() -> None:
    """Fix-G happy path: pa ≈ 0, pb ≈ 0.5 → window persists via the drift-only channel."""
    cps, velocities = _drift_only_inputs()
    settings = _settings_with(pipeline_b_mode="percentile")

    windows = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=velocities,
            baseline_similarity_curve=[],
            window_days=90,
            min_feature_ratio=0.99,  # ratio gate cannot save this single-family window
            total_feature_count=1,
            settings=settings,
        )
    )

    assert windows, "Fix-G: drift-only path should persist the high-pb window"
    window = windows[0]
    # pa is tiny — pre-Fix-G both ratio and AB gates would have rejected this.
    assert window.pipeline_a_score < 0.3
    assert window.pipeline_b_score >= 0.3
    assert window.passes_via == ["drift_only"], (
        f"expected pure drift-only admission, got {window.passes_via}"
    )


def test_drift_only_and_ab_both_admit_window() -> None:
    """Fix-G edge: pa just over 0.3 plus pb >= 0.3 → passes_via lists both gates in order."""
    cp_time = datetime(2024, 3, 15, tzinfo=UTC)
    # confidence * effect_size = 0.7 * 0.6 = 0.42 → pa ≈ 0.42 (above 0.3, below 0.5).
    cps = [_cp("ttr", cp_time, confidence=0.7, effect_size=0.6)]
    velocities = [(f"2024-{m:02d}", 0.1 * m) for m in range(1, 7)]
    settings = _settings_with(pipeline_b_mode="percentile")

    windows = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=velocities,
            baseline_similarity_curve=[],
            window_days=90,
            min_feature_ratio=0.99,  # ratio gate cannot save this single-family window
            total_feature_count=1,
            settings=settings,
        )
    )

    assert windows, "expected an admitted window"
    window = windows[0]
    assert window.pipeline_a_score > PIPELINE_SCORE_PASS_THRESHOLD
    assert window.pipeline_b_score >= 0.3
    # Insertion order in ``_score_single_window`` is ratio → ab → drift_only.
    assert window.passes_via == ["ab", "drift_only"], (
        f"expected ab + drift_only admission, got {window.passes_via}"
    )


def test_ratio_only_admission_marks_passes_via_ratio() -> None:
    """Fix-G regression: a window passing ONLY via the family-ratio gate keeps its label."""
    base = datetime(2024, 6, 1, tzinfo=UTC)
    feature_names = [
        "ttr",  # lexical_richness
        "flesch_kincaid",  # readability
        "sent_length_mean",  # sentence_structure
        "bigram_entropy",  # entropy
        "self_similarity_30d",  # self_similarity
        "ai_marker_frequency",  # ai_markers
    ]
    # Tiny per-CP score keeps pipeline_a below 0.3 while still hitting all
    # FAMILY_COUNT families so the ratio gate fires alone.
    cps = [
        _cp(name, base + timedelta(days=i * 3), confidence=0.1, effect_size=0.1)
        for i, name in enumerate(feature_names)
    ]

    windows = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.6,
            total_feature_count=len(feature_names),
            # Disable the drift-only channel by setting threshold above max pb.
            drift_only_pb_threshold=1.5,
        )
    )

    assert windows, "expected the family-ratio gate to admit at least one window"
    window = windows[0]
    assert window.pipeline_a_score < PIPELINE_SCORE_PASS_THRESHOLD, (
        "pipeline_a should be too low to clear the AB gate"
    )
    assert window.pipeline_b_score < 0.3, "no velocity/sim signal → pb stays at 0"
    assert window.passes_via == ["ratio"], f"expected pure ratio admission, got {window.passes_via}"
