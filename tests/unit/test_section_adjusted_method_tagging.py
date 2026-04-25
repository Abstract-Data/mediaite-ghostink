"""Phase 15 J5 — producer-side method-name retagging.

When ``settings.analysis.section_residualize_features=True``, the change-point
producer (:func:`forensics.analysis.changepoint.analyze_author_feature_changepoints`)
must tag emitted CPs with ``pelt_section_adjusted`` / ``bocpd_section_adjusted``
so the convergence dispatch and the K4 twin-panel renderer can distinguish
residualized output from raw PELT/BOCPD.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from forensics.analysis.changepoint import analyze_author_feature_changepoints
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig


def _settings(*, residualize: bool, methods: list[str]) -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(
            changepoint_methods=methods,
            section_residualize_features=residualize,
            min_articles_per_section_for_residualize=1,
        ),
    )


def _shifted_frame(*, n: int = 80, seed: int = 7) -> pl.DataFrame:
    """Frame with a deterministic mean-shift on `ttr` and a section column."""
    rng = np.random.default_rng(seed)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(n):
        shift = 1.8 if i >= n // 2 else 0.0
        rows.append(
            {
                "timestamp": base + timedelta(days=i),
                "ttr": float(shift + rng.normal(0.0, 0.25)),
                # Single section so residualization runs but does not zero the shift.
                "section": "news",
            }
        )
    return pl.DataFrame(rows)


def test_residualization_off_emits_raw_method_names() -> None:
    cps = analyze_author_feature_changepoints(
        _shifted_frame(),
        author_id="author-raw",
        settings=_settings(residualize=False, methods=["pelt"]),
    )
    assert cps, "fixture should produce at least one CP"
    assert {cp.method for cp in cps} <= {"pelt", "bocpd"}
    assert not any(cp.method.endswith("_section_adjusted") for cp in cps)


def test_residualization_on_retags_methods_section_adjusted() -> None:
    cps = analyze_author_feature_changepoints(
        _shifted_frame(),
        author_id="author-adj",
        settings=_settings(residualize=True, methods=["pelt", "bocpd"]),
    )
    assert cps, "fixture should still produce at least one residualized CP"
    methods = {cp.method for cp in cps}
    # Every emitted CP gets retagged — no bare pelt / bocpd should leak through
    # when residualization is on.
    assert methods <= {"pelt_section_adjusted", "bocpd_section_adjusted"}, methods
    assert not any(cp.method in {"pelt", "bocpd"} for cp in cps)
