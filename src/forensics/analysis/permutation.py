"""Permutation tests for convergence score significance.

Parametric p-values assume a null distribution shape (often Gaussian) that
convergence statistics do not obey. This module provides a non-parametric
alternative: shuffle labels/indices many times under the null hypothesis
and compare the observed statistic to the shuffled distribution.

Two entry points are exposed:

- ``permutation_test`` — generic empirical p-value against a pre-computed
  null distribution.
- ``changepoint_permutation`` — shuffle change-point locations within a
  time series and compare an observed max-cluster signal to the shuffled
  null.

Both are deterministic when ``seed`` is supplied (``numpy.random.default_rng``).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PermutationResult:
    """Outcome of a permutation test.

    Attributes:
        observed: The observed test statistic.
        p_value: Empirical ``(n_extreme + 1) / (n_permutations + 1)``.
        null_mean: Mean of the permuted null distribution.
        null_std: Sample standard deviation of the permuted null distribution.
        n_permutations: Number of shuffles actually performed.
    """

    observed: float
    p_value: float
    null_mean: float
    null_std: float
    n_permutations: int


def _empirical_p(observed: float, null: np.ndarray) -> float:
    """Two-sided-safe one-sided upper-tail empirical p-value.

    Uses the ``+1`` correction so the minimum p-value is never zero.
    """
    if null.size == 0:
        return 1.0
    n_extreme = int(np.sum(null >= observed))
    return (n_extreme + 1) / (null.size + 1)


def permutation_test(
    observed: float,
    null_distribution: Sequence[float],
    *,
    n_permutations: int = 1000,
) -> PermutationResult:
    """Empirical p-value for ``observed`` against a pre-computed null.

    The caller is responsible for providing a null distribution generated
    by the appropriate shuffling procedure for their statistic. This
    function only translates it into a :class:`PermutationResult`.

    Args:
        observed: The observed test statistic.
        null_distribution: A sequence of statistics computed under the null.
        n_permutations: Advisory count used when the null distribution is
            empty. When the null distribution is non-empty, its length
            wins — we never fabricate samples.

    Returns:
        :class:`PermutationResult` with the empirical p-value and the null
        distribution's mean/std. If ``null_distribution`` is empty, the
        result reports ``p_value=1.0`` and zero null moments.
    """
    null = np.asarray(null_distribution, dtype=float)

    if null.size == 0:
        logger.debug("permutation_test: empty null distribution; p=1.0 by convention")
        return PermutationResult(
            observed=float(observed),
            p_value=1.0,
            null_mean=0.0,
            null_std=0.0,
            n_permutations=n_permutations,
        )

    p_value = _empirical_p(float(observed), null)
    null_mean = float(np.mean(null))
    null_std = float(np.std(null, ddof=1)) if null.size > 1 else 0.0

    logger.debug(
        "permutation_test: observed=%.4f p=%.4f null_mean=%.4f null_std=%.4f n=%d",
        observed,
        p_value,
        null_mean,
        null_std,
        null.size,
    )
    return PermutationResult(
        observed=float(observed),
        p_value=p_value,
        null_mean=null_mean,
        null_std=null_std,
        n_permutations=null.size,
    )


def _max_window_density(
    changepoint_indices: np.ndarray,
    series_length: int,
    window: int,
) -> float:
    """Max fraction of change-points that fall within any window of size ``window``.

    Used as the observed / null test statistic for
    :func:`changepoint_permutation`. Higher density means more clustered.
    """
    if changepoint_indices.size == 0 or series_length <= 0:
        return 0.0
    if window <= 0:
        return 0.0

    sorted_idx = np.sort(changepoint_indices)
    max_count = 0
    left = 0
    for right in range(sorted_idx.size):
        while sorted_idx[right] - sorted_idx[left] >= window:
            left += 1
        count = right - left + 1
        if count > max_count:
            max_count = count
    return max_count / float(sorted_idx.size)


def changepoint_permutation(
    series: np.ndarray,
    changepoints: Sequence[int],
    *,
    n_permutations: int = 1000,
    seed: int | None = 42,
    window: int | None = None,
) -> PermutationResult:
    """Permutation test for change-point clustering in a time series.

    Null hypothesis: the observed change-points are uniformly distributed
    over the series — they do not cluster temporally any more than random
    draws from the same length would.

    Test statistic: the maximum fraction of change-points contained in
    any sliding window of ``window`` samples. Clustered change-points
    produce a high observed statistic; scattered ones do not.

    Args:
        series: The underlying 1-D signal. Only its length is used.
        changepoints: Observed change-point indices in ``series``.
        n_permutations: Number of shuffles to draw for the null.
        seed: RNG seed. Pin for determinism; ``None`` uses fresh entropy.
        window: Sliding-window width. Defaults to ``len(series) // 10``
            (or 1 for very short series).

    Returns:
        :class:`PermutationResult`. For an empty ``changepoints`` input the
        observed statistic is 0 and the p-value is ``1.0`` by convention.
    """
    n = int(series.shape[0]) if hasattr(series, "shape") else len(series)
    cps = np.asarray(changepoints, dtype=int)
    k = cps.size

    if k == 0 or n <= 0:
        logger.debug("changepoint_permutation: no changepoints; returning sentinel p=1.0")
        return PermutationResult(
            observed=0.0,
            p_value=1.0,
            null_mean=0.0,
            null_std=0.0,
            n_permutations=0,
        )

    win = window if window is not None else max(1, n // 10)
    observed = _max_window_density(cps, n, win)

    rng = np.random.default_rng(seed)
    null = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        shuffled = rng.choice(n, size=k, replace=False)
        null[i] = _max_window_density(shuffled, n, win)

    p_value = _empirical_p(observed, null)
    logger.debug(
        "changepoint_permutation: observed=%.4f p=%.4f n_cp=%d n=%d window=%d",
        observed,
        p_value,
        k,
        n,
        win,
    )
    return PermutationResult(
        observed=float(observed),
        p_value=p_value,
        null_mean=float(np.mean(null)),
        null_std=float(np.std(null, ddof=1)) if null.size > 1 else 0.0,
        n_permutations=n_permutations,
    )


__all__ = [
    "PermutationResult",
    "changepoint_permutation",
    "permutation_test",
]
