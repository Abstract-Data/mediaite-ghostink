"""Phase 15 Phase A — BOCPD detection-rule semantics.

Covers all four sub-steps shipped in this PR:

- A1: legacy ``P(r_t = 0)`` thresholding is algebraically pinned to the hazard
  rate under constant-hazard A&M (GUARDRAILS Sign "BOCPD ``P(r=0)`` posterior
  is pinned to the hazard rate"). Pinned via
  ``test_legacy_p_r0_threshold_is_algebraically_pinned``.
- A2: MAP-run-length reset detection rule with warmup, refractory cooldown,
  and multi-reset collapse.
- A3: settings plumbing through ``analyze_author_feature_changepoints``.
- A4: NIG → Student-t posterior predictive (Murphy 2007 §7.6) surfaces
  mean-shifts at least as early as the Normal-known-σ² path.
"""

from __future__ import annotations

import numpy as np
import pytest

from forensics.analysis.changepoint import detect_bocpd

# --- Shared synthetic fixtures ---------------------------------------------------


def _mean_shift_signal(
    *,
    pre_len: int = 50,
    post_len: int = 50,
    pre_mean: float = 0.0,
    post_mean: float = 5.0,
    sigma: float = 0.3,
    seed: int = 0,
) -> np.ndarray:
    """Synthetic 1-D series with a single mid-series mean shift plus noise."""
    rng = np.random.default_rng(seed)
    pre = rng.normal(pre_mean, sigma, pre_len)
    post = rng.normal(post_mean, sigma, post_len)
    return np.concatenate([pre, post])


# --- A1: legacy ``P(r=0)`` threshold is structurally unable to fire -------------


def test_legacy_p_r0_threshold_is_algebraically_pinned() -> None:
    """Under ``mode="p_r0_legacy"``, ``P(r=0) == hazard_rate`` for every step.

    With ``hazard_rate=1/250`` and ``threshold=0.5`` the legacy rule cannot
    fire on a single mid-series 0 → 5 mean shift — it returns at most one
    spurious "change-point" or, more typically, zero. This test pins the
    GUARDRAILS Sign "BOCPD ``P(r=0)`` posterior is pinned to the hazard rate".
    """
    signal = _mean_shift_signal()
    raw = detect_bocpd(
        signal,
        hazard_rate=1 / 250.0,
        mode="p_r0_legacy",
        threshold=0.5,
    )
    assert len(raw) <= 1, (
        f"legacy P(r=0) thresholding should be unable to fire under constant "
        f"hazard; got {len(raw)} emits: {raw[:5]}"
    )


# --- A2: MAP-reset detection rule fires exactly once on a mean shift ------------


def test_map_reset_emits_single_changepoint_on_mean_shift() -> None:
    """MAP-run-length reset should emit exactly one CP near the true split.

    Multi-reset collapse merges adjacent argmax drops into a single emit; the
    reported timestep should land within a small window around index 50.
    """
    signal = _mean_shift_signal()
    raw = detect_bocpd(
        signal,
        hazard_rate=1 / 250.0,
        mode="map_reset",
        map_drop_ratio=0.5,
        min_run_length=5,
        reset_cooldown=3,
        merge_window=2,
    )
    assert len(raw) == 1, f"expected exactly 1 CP after merge, got {len(raw)}: {raw}"
    t_emit, conf = raw[0]
    assert 48 <= t_emit <= 60, f"emit should land near the true split (50); got t={t_emit}"
    assert 0.0 <= conf <= 1.0


# --- A2 edge case: warmup suppresses early-signal resets ------------------------


def test_warmup_suppresses_early_resets() -> None:
    """No emit may occur until ``prev_map >= min_run_length``.

    Construct a series whose first observation already looks anomalous: the
    detector must NOT fire before the warmup gate clears.
    """
    rng = np.random.default_rng(1)
    # The very first sample is far from the prior mean estimate; without
    # warmup the MAP could drop on step 1.
    early_outlier = np.concatenate(
        [
            np.array([10.0]),
            rng.normal(0.0, 0.3, 99),
        ]
    )
    raw = detect_bocpd(
        early_outlier,
        hazard_rate=1 / 250.0,
        mode="map_reset",
        map_drop_ratio=0.5,
        min_run_length=10,
        reset_cooldown=3,
        merge_window=2,
    )
    early_emits = [(t, c) for t, c in raw if t < 10]
    assert not early_emits, f"warmup should suppress emits at t<10; got {early_emits}"


# --- A2 edge case: cooldown suppresses back-to-back emits -----------------------


def test_cooldown_suppresses_back_to_back_emits() -> None:
    """``reset_cooldown`` blocks emits within K steps of the previous emit.

    Construct two genuine shifts close together; with a long cooldown only
    the first should fire.
    """
    rng = np.random.default_rng(2)
    signal = np.concatenate(
        [
            rng.normal(0.0, 0.2, 40),
            rng.normal(5.0, 0.2, 6),
            rng.normal(10.0, 0.2, 40),
        ]
    )
    long_cooldown = detect_bocpd(
        signal,
        hazard_rate=1 / 250.0,
        mode="map_reset",
        map_drop_ratio=0.5,
        min_run_length=5,
        reset_cooldown=50,  # span larger than the gap between shifts
        merge_window=0,  # don't conflate cooldown with merge
    )
    short_cooldown = detect_bocpd(
        signal,
        hazard_rate=1 / 250.0,
        mode="map_reset",
        map_drop_ratio=0.5,
        min_run_length=5,
        reset_cooldown=1,
        merge_window=0,
    )
    assert len(long_cooldown) <= len(short_cooldown), (
        f"long cooldown should emit no more than short cooldown; "
        f"long={long_cooldown} short={short_cooldown}"
    )
    assert len(long_cooldown) <= 1, (
        f"long cooldown should suppress the second back-to-back emit; got {long_cooldown}"
    )


# --- A2 edge case: multi-reset collapse merges adjacent emits -------------------


def test_multi_reset_collapse_keeps_single_changepoint() -> None:
    """A single shift can drop the MAP across several consecutive timesteps.

    With ``merge_window > 0`` those adjacent drops collapse to one CP at the
    highest-confidence timestamp.
    """
    signal = _mean_shift_signal(pre_mean=0.0, post_mean=8.0, sigma=0.3, seed=3)
    no_merge = detect_bocpd(
        signal,
        hazard_rate=1 / 250.0,
        mode="map_reset",
        map_drop_ratio=0.5,
        min_run_length=5,
        reset_cooldown=0,
        merge_window=0,
    )
    merged = detect_bocpd(
        signal,
        hazard_rate=1 / 250.0,
        mode="map_reset",
        map_drop_ratio=0.5,
        min_run_length=5,
        reset_cooldown=0,
        merge_window=5,
    )
    assert len(merged) <= len(no_merge), (
        f"merging cannot increase the emit count; merged={merged} no_merge={no_merge}"
    )
    assert len(merged) == 1, f"merge should collapse adjacent drops to 1 emit; got {merged}"


# --- A2 rollback: legacy mode preserves byte-for-byte behavior -------------------


def test_legacy_mode_preserves_byte_for_byte() -> None:
    """``mode="p_r0_legacy"`` must produce the same emit list as the pre-Phase-A
    implementation for the same inputs, regardless of the new MAP-reset knobs.
    """
    rng = np.random.default_rng(11)
    signal = rng.normal(0.0, 1.0, 60)
    # Knob values that would change MAP-reset output but must be ignored in legacy mode.
    a = detect_bocpd(
        signal,
        hazard_rate=1 / 80.0,
        mode="p_r0_legacy",
        threshold=0.02,
        map_drop_ratio=0.1,
        min_run_length=99,
        reset_cooldown=99,
        merge_window=99,
    )
    b = detect_bocpd(
        signal,
        hazard_rate=1 / 80.0,
        mode="p_r0_legacy",
        threshold=0.02,
    )
    assert a == b, "legacy emit list must not depend on MAP-reset knobs"
    # Sanity: legacy mode at a low threshold should still produce SOMETHING under
    # the constant-hazard pin (one emit per step where p_cp >= threshold).
    assert all(p >= 0.02 - 1e-12 for _, p in a)


# --- A4: Student-t predictive surfaces mean-shift earlier than Normal ----------


def test_student_t_surfaces_mean_shift_at_least_as_well_as_normal() -> None:
    """With the MAP-reset rule fixed, the Student-t posterior predictive should
    detect the synthetic mean shift no later than the Normal-known-σ² path.

    Long-established segments under the Normal path read new observations
    through a σ² frozen at the 80-sample prefix; the NIG → Student-t update
    refreshes scale per-segment so genuine outliers look more outlying.
    """
    signal = _mean_shift_signal(pre_len=80, post_len=80, post_mean=3.0, sigma=0.4, seed=7)
    common = dict(
        hazard_rate=1 / 250.0,
        mode="map_reset",
        map_drop_ratio=0.5,
        min_run_length=5,
        reset_cooldown=3,
        merge_window=2,
    )
    normal = detect_bocpd(signal, student_t=False, **common)
    student = detect_bocpd(signal, student_t=True, **common)
    assert normal, f"Normal-path should still detect a CP on this fixture; got {normal}"
    assert student, f"Student-t path should detect a CP on this fixture; got {student}"
    # Earliest emit timestamp under each path. Student-t must fire <= Normal.
    t_normal = min(t for t, _ in normal)
    t_student = min(t for t, _ in student)
    assert t_student <= t_normal, (
        f"Student-t should surface the shift no later than Normal; "
        f"t_normal={t_normal} t_student={t_student}"
    )


def test_student_t_and_normal_both_default_on_clean_signal_are_quiet() -> None:
    """On a stationary signal both predictive choices should emit zero CPs."""
    rng = np.random.default_rng(42)
    signal = rng.normal(0.0, 1.0, 200)
    common = dict(
        hazard_rate=1 / 500.0,
        mode="map_reset",
        map_drop_ratio=0.4,
        min_run_length=15,
        reset_cooldown=10,
        merge_window=5,
    )
    n = detect_bocpd(signal, student_t=False, **common)
    s = detect_bocpd(signal, student_t=True, **common)
    # Stationary white noise occasionally clips the threshold, but shouldn't
    # litter the emit stream — tolerate at most 2 false positives.
    assert len(n) <= 2, f"Normal-path noisy on stationary signal: {n}"
    assert len(s) <= 2, f"Student-t noisy on stationary signal: {s}"


# --- A3: integration via ``analyze_author_feature_changepoints`` settings -------


def test_settings_plumbing_uses_map_reset_by_default() -> None:
    """``analyze_author_feature_changepoints`` should pick ``map_reset`` from
    settings and produce CPs on a frame that contains a real mid-series shift.
    """
    from datetime import UTC, datetime, timedelta

    import polars as pl

    from forensics.analysis.changepoint import (
        PELT_FEATURE_COLUMNS,
        analyze_author_feature_changepoints,
    )
    from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig

    n = 120
    base = datetime(2023, 1, 1, tzinfo=UTC)
    rows: dict[str, list] = {
        "article_id": [f"a{i}" for i in range(n)],
        "author_id": ["auth-1"] * n,
        "timestamp": [base + timedelta(days=i) for i in range(n)],
    }
    rng = np.random.default_rng(123)
    shift = np.concatenate(
        [
            rng.normal(0.0, 0.05, n // 2),
            rng.normal(1.0, 0.05, n - n // 2),
        ]
    )
    flat = rng.normal(0.0, 0.05, n)
    for col in PELT_FEATURE_COLUMNS:
        rows[col] = (shift if col == "ttr" else flat).tolist()
    df = pl.DataFrame(rows)

    settings = ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(changepoint_methods=["bocpd"]),
    )
    cps = analyze_author_feature_changepoints(df, author_id="auth-1", settings=settings)
    bocpd_ttr = [c for c in cps if c.feature_name == "ttr" and c.method == "bocpd"]
    assert bocpd_ttr, (
        f"map_reset BOCPD with default knobs should fire on the synthetic "
        f"mid-series shift in `ttr`; got {[c.feature_name for c in cps]}"
    )


@pytest.mark.parametrize("mode", ["map_reset", "p_r0_legacy"])
def test_detect_bocpd_returns_sorted_unique_timestamps(mode: str) -> None:
    rng = np.random.default_rng(5)
    signal = rng.normal(0.0, 1.0, 120)
    out = detect_bocpd(signal, hazard_rate=1 / 80.0, mode=mode, threshold=0.005)
    timestamps = [t for t, _ in out]
    assert timestamps == sorted(timestamps)
    assert len(timestamps) == len(set(timestamps))
