"""Phase 15 C1 — KS test is dropped from the default hypothesis battery.

Per-CP test count drops 3 → 2 (Welch + Mann–Whitney). KS detects
distribution-shape changes; the forensic analysis cares about location
shifts which Welch and Mann–Whitney already cover. The KS branch is gated
behind ``AnalysisConfig.enable_ks_test`` so reviewers can re-enable it for
replication runs without code changes.
"""

from __future__ import annotations

from forensics.analysis.statistics import run_hypothesis_tests
from forensics.config.settings import AnalysisConfig

# Deterministic fixture: a clear location shift so Welch + Mann–Whitney
# both produce finite, low p-values without relying on randomness.
_PRE = [1.0, 1.1, 0.9, 1.2, 0.95, 1.05, 1.1, 0.9]
_POST = [5.0, 5.1, 4.9, 5.2, 4.95, 5.05, 5.1, 4.9]
_FEATURE = "ttr"
_AUTHOR = "author-x"


def _run_default() -> list:
    return run_hypothesis_tests(
        _PRE + _POST,
        len(_PRE),
        _FEATURE,
        _AUTHOR,
        n_bootstrap=50,
    )


def test_default_battery_excludes_ks_2samp() -> None:
    """Happy path: default behaviour must not emit a ``ks_2samp`` test."""
    tests = _run_default()
    assert tests, "fixture must produce hypothesis tests"
    assert all(not t.test_name.startswith("ks_2samp") for t in tests)
    # Welch and Mann–Whitney remain.
    prefixes = {t.test_name.split("_")[0] for t in tests}
    assert "welch" in prefixes
    assert "mann" in prefixes


def test_enable_ks_test_flag_reintroduces_ks_branch() -> None:
    """Edge case: ``enable_ks_test=True`` re-adds the KS row for replication."""
    tests_off = _run_default()
    tests_on = run_hypothesis_tests(
        _PRE + _POST,
        len(_PRE),
        _FEATURE,
        _AUTHOR,
        n_bootstrap=50,
        enable_ks_test=True,
    )
    assert len(tests_on) == len(tests_off) + 1
    ks_rows = [t for t in tests_on if t.test_name.startswith("ks_2samp")]
    assert len(ks_rows) == 1
    ks = ks_rows[0]
    assert ks.feature_name == _FEATURE
    assert ks.author_id == _AUTHOR
    assert 0.0 <= ks.raw_p_value <= 1.0


def test_default_battery_count_and_order_pinned() -> None:
    """Regression-pin: lock the count and ordering of the default battery.

    If a future change re-enables KS by default or reorders the battery,
    this test fires loudly. Reviewers can spot-check before updating.
    """
    tests = _run_default()
    assert len(tests) == 2
    # Welch t comes first, Mann–Whitney second. Names are feature-scoped.
    assert tests[0].test_name == f"welch_t_{_FEATURE}"
    assert tests[1].test_name == f"mann_whitney_{_FEATURE}"
    for t in tests:
        assert t.feature_name == _FEATURE
        assert t.author_id == _AUTHOR


def test_analysis_config_default_disables_ks() -> None:
    """Settings default keeps KS off; replication runs flip it explicitly."""
    cfg = AnalysisConfig()
    assert cfg.enable_ks_test is False
