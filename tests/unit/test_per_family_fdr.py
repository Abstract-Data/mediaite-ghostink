"""Per-family FDR grouping (Phase 15 C2).

Validates :func:`forensics.analysis.statistics.apply_correction_grouped`:
- empty families don't crash,
- singleton families return raw p-values unchanged,
- per-family BH reclaims significance versus a single author-wide BH run.
"""

from __future__ import annotations

import pytest

from forensics.analysis.statistics import (
    apply_correction,
    apply_correction_grouped,
)
from forensics.models.analysis import HypothesisTest


def _mk(
    feature: str,
    raw_p: float,
    *,
    author: str = "a",
    effect: float = 0.5,
) -> HypothesisTest:
    return HypothesisTest(
        test_name=f"welch_t_{feature}",
        feature_name=feature,
        author_id=author,
        raw_p_value=raw_p,
        corrected_p_value=raw_p,
        effect_size_cohens_d=effect,
        confidence_interval_95=(0.0, 1.0),
        significant=False,
    )


def _by_feature(family_map: dict[str, str]):
    def _key(t: HypothesisTest) -> str:
        return family_map.get(t.feature_name, "unknown")

    return _key


def test_empty_family_skipped() -> None:
    """Family with zero tests never triggers the BH call (``defaultdict`` invariant).

    Also asserts :func:`apply_correction_grouped` on an empty input returns
    ``[]`` without raising. If future refactors introduce a pre-populated
    families dict, the ``if not group: continue`` branch inside
    :func:`apply_correction_grouped` guarantees we skip empty buckets.
    """
    assert apply_correction_grouped([], group_key=lambda t: "noop") == []

    # Single family populated; ``group_key`` deliberately returns a new label
    # for every test so each "family" is a singleton — a family that never
    # shows up in the output because no test maps to it would need a pre-
    # populated dict. We simulate the "family with zero tests" scenario by
    # relying on ``defaultdict`` semantics: groups that never see a test
    # never get created. No crash, no extra output.
    tests = [_mk("x", 0.01)]
    out = apply_correction_grouped(tests, group_key=lambda _t: "sole")
    assert len(out) == 1


def test_singleton_family_raw_p_returned() -> None:
    """Singleton family: BH is a no-op (``n == 1``), corrected == raw."""
    family_map = {"only_feature": "family_A"}
    tests = [_mk("only_feature", raw_p=0.03)]
    out = apply_correction_grouped(
        tests,
        group_key=_by_feature(family_map),
        method="benjamini_hochberg",
        alpha=0.05,
    )
    assert len(out) == 1
    assert out[0].corrected_p_value == pytest.approx(0.03)
    assert out[0].raw_p_value == pytest.approx(0.03)
    assert out[0].significant is True  # 0.03 < 0.05


def test_multi_family_increases_significance_over_author_grouping() -> None:
    """Per-family BH recovers signal that author-wide BH over-corrects away.

    Fixture: 20 tests across 4 families (5 per family). Each family has one
    small p near the BH-borderline; the other four are large. Under
    author-wide BH (n=20) the denominator inflates and kills the small
    p-values; under per-family BH (n=5 each) they survive.
    """
    family_map: dict[str, str] = {}
    tests: list[HypothesisTest] = []
    # Fixture geometry: 4 families × 5 tests = 20 hypotheses.
    #
    # Two "positive" families each carry one marginal p-value (0.008) that
    # beats the per-family BH rank-1 threshold (1 * 0.05 / 5 = 0.01) but
    # fails the author-wide rank-2 threshold (2 * 0.05 / 20 = 0.005 under
    # step-up monotonicity — the step-up lifts both to 0.008 * 20 / 2 = 0.08,
    # above alpha). The two "null" families contain only large p-values.
    #
    # Expected: per-family BH marks 2 tests significant, author-wide BH
    # marks 0. If a future refactor of :func:`apply_correction` changes the
    # step-up direction this fixture will break loudly — that's the point.
    positive_families = ("fam_A", "fam_B")
    null_families = ("fam_C", "fam_D")
    large_ps = [0.40, 0.55, 0.70, 0.80]
    for fam in positive_families:
        small_feature = f"{fam}_headline"
        family_map[small_feature] = fam
        tests.append(_mk(small_feature, raw_p=0.008))
        for i, lp in enumerate(large_ps):
            name = f"{fam}_noise_{i}"
            family_map[name] = fam
            tests.append(_mk(name, raw_p=lp))
    for fam in null_families:
        for i, lp in enumerate(large_ps + [0.35]):
            name = f"{fam}_noise_{i}"
            family_map[name] = fam
            tests.append(_mk(name, raw_p=lp))

    author_wide = apply_correction(
        tests,
        method="benjamini_hochberg",
        alpha=0.05,
    )
    per_family = apply_correction_grouped(
        tests,
        group_key=_by_feature(family_map),
        method="benjamini_hochberg",
        alpha=0.05,
    )

    author_sig = sum(1 for t in author_wide if t.significant)
    family_sig = sum(1 for t in per_family if t.significant)
    assert family_sig > author_sig, (
        f"per-family BH ({family_sig} sig) should beat author-wide BH "
        f"({author_sig} sig) on a fixture engineered for correlated families"
    )


def test_grouped_is_stable_with_legacy_when_single_family() -> None:
    """Sanity: one family only => identical output to plain ``apply_correction``."""
    tests = [_mk(f"f{i}", raw_p=p) for i, p in enumerate((0.001, 0.02, 0.04, 0.3))]
    grouped = apply_correction_grouped(
        tests,
        group_key=lambda _t: "sole",
        method="benjamini_hochberg",
        alpha=0.05,
    )
    flat = apply_correction(tests, method="benjamini_hochberg", alpha=0.05)
    assert [t.corrected_p_value for t in grouped] == [t.corrected_p_value for t in flat]
    assert [t.significant for t in grouped] == [t.significant for t in flat]
