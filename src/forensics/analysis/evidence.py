"""Shared evidence gates for confirmatory analysis outputs."""

from __future__ import annotations

from collections.abc import Iterable

from forensics.config.settings import AnalysisConfig
from forensics.models.analysis import ChangePoint

MIN_EVIDENCE_CONFIDENCE = 0.9
# PELT's ``confidence`` field is a sigmoid of |d| (``|d| / (|d| + 1)``), which
# saturates around 0.95 even for huge effects — it is a quality ranking, not
# a probability. Applying ``MIN_EVIDENCE_CONFIDENCE = 0.9`` to PELT effectively
# drops every PELT change-point regardless of effect size.
# PELT CPs are admitted on effect-size strength alone, but with a ``very
# large`` floor (Cohen's d ≥ 1.0). This is intentionally conservative:
# without this floor PELT detected ~50 CPs per author on continuous
# stylistic features (TTR, sentence length, readability) at medium effect
# sizes — those reflect normal writing variation over 5 years, not AI
# adoption. d ≥ 1.0 reserves PELT for genuine regime shifts that
# corroborate BOCPD (whose posterior probability already gates noise).
_PELT_MIN_EFFECT_SIZE = 1.0
_PELT_METHODS: frozenset[str] = frozenset({"pelt", "pelt_section_adjusted"})


def filter_evidence_change_points(
    change_points: Iterable[ChangePoint],
    analysis_cfg: AnalysisConfig,
    *,
    min_confidence: float = MIN_EVIDENCE_CONFIDENCE,
) -> list[ChangePoint]:
    """Keep only change-points strong enough to count as confirmatory evidence.

    BOCPD CPs use posterior probability as ``confidence`` — gated on
    ``min_confidence`` AND ``effect_size_threshold``.

    PELT CPs use a sigmoid-of-d quality score that cannot reach 0.9 — gated
    on ``max(effect_size_threshold, _PELT_MIN_EFFECT_SIZE)`` only.
    """
    cohort: list[ChangePoint] = []
    for cp in change_points:
        d_abs = abs(cp.effect_size_cohens_d)
        if cp.method in _PELT_METHODS:
            if d_abs >= max(analysis_cfg.effect_size_threshold, _PELT_MIN_EFFECT_SIZE):
                cohort.append(cp)
            continue
        if cp.confidence >= min_confidence and d_abs >= analysis_cfg.effect_size_threshold:
            cohort.append(cp)
    return cohort
