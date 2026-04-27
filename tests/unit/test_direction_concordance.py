"""Unit tests for :func:`classify_direction_concordance` and tie collapse rules."""

from __future__ import annotations

from datetime import date

import pytest

from forensics.models.analysis import ConvergenceWindow, HypothesisTest
from forensics.models.report import (
    DirectionBreakdown,
    DirectionConcordance,
    classify_direction_concordance,
)


def _window() -> ConvergenceWindow:
    return ConvergenceWindow(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
        features_converging=["ttr"],
        convergence_ratio=0.5,
        pipeline_a_score=0.5,
        pipeline_b_score=0.5,
    )


def _ht(
    *,
    feature: str,
    d: float,
    test_name: str = "welch",
    author: str = "author-a",
) -> HypothesisTest:
    return HypothesisTest(
        test_name=test_name,
        feature_name=feature,
        author_id=author,
        raw_p_value=0.01,
        corrected_p_value=0.02,
        effect_size_cohens_d=d,
        confidence_interval_95=(-0.1, 0.1),
        significant=True,
        n_pre=10,
        n_post=10,
    )


def test_empty_tests_returns_na() -> None:
    conc, br = classify_direction_concordance(_window(), [])
    assert conc == DirectionConcordance.NA
    assert br == DirectionBreakdown(
        n_match=0,
        n_oppose=0,
        n_no_prior=0,
        matched_features=tuple(),
        opposed_features=tuple(),
    )


def test_only_unknown_feature_names_no_priors_returns_na() -> None:
    tests = [
        _ht(feature="not_in_priors_registry_xyz", d=0.5),
    ]
    conc, br = classify_direction_concordance(_window(), tests)
    assert conc == DirectionConcordance.NA
    assert br.n_no_prior == 1
    assert br.n_match == 0 and br.n_oppose == 0


def test_hedging_frequency_counts_as_no_prior() -> None:
    tests = [_ht(feature="hedging_frequency", d=0.8)]
    conc, br = classify_direction_concordance(_window(), tests)
    assert conc == DirectionConcordance.NA
    assert br.n_no_prior == 1


def test_zero_cohens_d_observed_none_treated_as_no_prior() -> None:
    """``direction_from_d(0)`` is None — feature does not enter match/oppose tallies."""
    tests = [_ht(feature="ttr", d=0.0)]
    conc, br = classify_direction_concordance(_window(), tests)
    assert conc == DirectionConcordance.NA
    assert br.n_no_prior == 1


def test_single_prior_feature_match_is_ai() -> None:
    # ttr prior is decrease; negative d => decrease => match
    conc, br = classify_direction_concordance(_window(), [_ht(feature="ttr", d=-0.4)])
    assert conc == DirectionConcordance.AI
    assert br.n_match == 1 and br.n_oppose == 0
    assert br.matched_features == ("ttr",)


def test_single_prior_feature_oppose_is_non_ai() -> None:
    conc, br = classify_direction_concordance(_window(), [_ht(feature="ttr", d=0.4)])
    assert conc == DirectionConcordance.NON_AI
    assert br.n_oppose == 1 and br.n_match == 0
    assert br.opposed_features == ("ttr",)


def test_fifty_percent_threshold_two_features_one_one_is_ai() -> None:
    """1 match + 1 oppose => 50% match => AI (``n_match * 2 >= prior_total``)."""
    tests = [
        _ht(feature="ttr", d=-0.5),  # match (decrease)
        _ht(feature="coleman_liau", d=-0.5),  # oppose (increase prior)
    ]
    conc, br = classify_direction_concordance(_window(), tests)
    assert conc == DirectionConcordance.AI
    assert br.n_match == 1 and br.n_oppose == 1


def test_mixed_when_some_match_but_below_half() -> None:
    """1 match, 2 oppose => 1/3 < 50% but n_match > 0 => MIXED."""
    tests = [
        _ht(feature="ttr", d=-0.5),
        _ht(feature="coleman_liau", d=-0.5),
        _ht(feature="gunning_fog", d=-0.5),
    ]
    conc, br = classify_direction_concordance(_window(), tests)
    assert conc == DirectionConcordance.MIXED
    assert br.n_match == 1 and br.n_oppose == 2


def test_collapse_per_feature_keeps_max_abs_d() -> None:
    tests = [
        _ht(feature="ttr", d=0.1, test_name="small"),
        _ht(feature="ttr", d=-0.9, test_name="large"),
    ]
    conc, br = classify_direction_concordance(_window(), tests)
    assert conc == DirectionConcordance.AI
    assert br.n_match == 1
    assert br.matched_features == ("ttr",)


def test_tie_abs_d_lexicographic_test_name_wins() -> None:
    """Tie on |d|: smaller ``test_name`` replaces (see ``_strictly_stronger_hypothesis``)."""
    tests = [
        _ht(feature="ttr", d=0.5, test_name="zebra"),
        _ht(feature="ttr", d=-0.5, test_name="apple"),
    ]
    conc, br = classify_direction_concordance(_window(), tests)
    # apple wins (same abs d, "apple" < "zebra") => d = -0.5 => match for ttr
    assert conc == DirectionConcordance.AI
    assert br.n_match == 1


@pytest.mark.parametrize(
    ("tests", "expected"),
    [
        (
            [_ht(feature="ttr", d=-0.5), _ht(feature="coleman_liau", d=0.5)],
            DirectionConcordance.AI,
        ),
        (
            [_ht(feature="ttr", d=0.5), _ht(feature="coleman_liau", d=-0.5)],
            DirectionConcordance.NON_AI,
        ),
    ],
)
def test_two_features_all_match_or_all_oppose(
    tests: list[HypothesisTest],
    expected: DirectionConcordance,
) -> None:
    conc, _ = classify_direction_concordance(_window(), tests)
    assert conc == expected
