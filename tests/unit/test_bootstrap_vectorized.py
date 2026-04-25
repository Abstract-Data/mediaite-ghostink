"""Phase 15 F1 — vectorized ``bootstrap_ci``.

The pre-F1 implementation drove a Python ``for _ in range(n_bootstrap)`` loop
that called ``rng.choice`` twice per iteration (once per group), so each
iteration consumed RNG state in an interleaved (a, b, a, b, ...) order. F1
replaces the loop with a single ``rng.choice(..., size=(n_bootstrap, n))``
per group; that draws all ``n_bootstrap`` rows for ``a`` first, then all rows
for ``b``. The change is intentional and ships its own pinned reference
values — the loop and vectorized forms cannot agree bit-for-bit at the same
seed because they consume the RNG stream in different orders.

Per the H1 spec these tests cover:

* **Regression-pin:** for the spec's fixed ``(a, b, seed)`` triple, the
  vectorized output is locked to ``(_REF_LO, _REF_HI)``. Any future change
  that intentionally alters output (BCa, percentile-t, different sampling
  shape) must update these constants deliberately.
* **Edge case:** an empty group on either side returns ``(0.0, 0.0)``
  cleanly — no exception, no NaN.
* **Determinism:** repeat calls with the same seed return identical tuples,
  and different seeds return different tuples (sanity-check that the seed
  is actually threaded through ``np.random.default_rng``).
"""

from __future__ import annotations

import numpy as np
import pytest

from forensics.analysis.statistics import bootstrap_ci

# ---------------------------------------------------------------------------
# Regression pin — captured once from the post-F1 vectorized implementation
# (2026-04-24) on the spec's fixed (a, b, seed) triple. Bumping these values
# must be a deliberate decision, not silent drift.
# ---------------------------------------------------------------------------
_REF_LO = 0.2601315351229742
_REF_HI = 1.1295517416236465


@pytest.fixture
def fixed_seed_inputs() -> tuple[list[float], list[float]]:
    """Spec fixture (lines 1058-1063): two normal samples drawn from default_rng(0)."""
    rng = np.random.default_rng(0)
    a = rng.normal(0.0, 1.0, size=30).tolist()
    b = rng.normal(0.3, 1.0, size=40).tolist()
    return a, b


# ---------------------------------------------------------------------------
# Regression-pin
# ---------------------------------------------------------------------------


def test_vectorized_matches_pinned_reference(
    fixed_seed_inputs: tuple[list[float], list[float]],
) -> None:
    """Vectorized output is bit-for-bit pinned to ``(_REF_LO, _REF_HI)``."""
    a, b = fixed_seed_inputs
    lo_new, hi_new = bootstrap_ci(a, b, n_bootstrap=200, seed=42)
    assert (lo_new, hi_new) == pytest.approx(
        (_REF_LO, _REF_HI),
        rel=1e-12,
        abs=1e-12,
    )


# ---------------------------------------------------------------------------
# Edge case
# ---------------------------------------------------------------------------


def test_empty_group_returns_zero_zero() -> None:
    """Either side empty → ``(0.0, 0.0)``, no exception."""
    nonempty = [0.1, 0.2, 0.3, 0.4]
    assert bootstrap_ci([], nonempty) == (0.0, 0.0)
    assert bootstrap_ci(nonempty, []) == (0.0, 0.0)
    assert bootstrap_ci([], []) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Determinism — same seed reproduces, different seed diverges
# ---------------------------------------------------------------------------


def test_same_seed_is_deterministic_across_runs(
    fixed_seed_inputs: tuple[list[float], list[float]],
) -> None:
    """Two calls with the same seed produce identical outputs."""
    a, b = fixed_seed_inputs
    first = bootstrap_ci(a, b, n_bootstrap=300, seed=2026)
    second = bootstrap_ci(a, b, n_bootstrap=300, seed=2026)
    assert first == second


def test_different_seed_changes_output(
    fixed_seed_inputs: tuple[list[float], list[float]],
) -> None:
    """Different seeds must yield different CIs (sanity-check seed is threaded)."""
    a, b = fixed_seed_inputs
    seed_a = bootstrap_ci(a, b, n_bootstrap=300, seed=1)
    seed_b = bootstrap_ci(a, b, n_bootstrap=300, seed=2)
    assert seed_a != seed_b
