"""BH cross-author tie stability: identical minima order by slug, not dict iteration."""

from __future__ import annotations

from forensics.analysis.statistics import apply_cross_author_correction
from forensics.models.analysis import HypothesisTest


def _ttr_test(*, author: str, corrected: float) -> HypothesisTest:
    return HypothesisTest(
        test_name="welch_t_ttr",
        feature_name="ttr",
        author_id=author,
        raw_p_value=corrected,
        corrected_p_value=corrected,
        effect_size_cohens_d=0.5,
        confidence_interval_95=(0.0, 1.0),
        significant=False,
        n_pre=10,
        n_post=10,
    )


def test_cross_author_bh_identical_pmin_stable_across_input_slug_order() -> None:
    """Tied author-level minima: BH-adjusted cross-author *p* is invariant to dict key order."""
    p_tie = 0.03
    t_zebra = _ttr_test(author="1", corrected=p_tie)
    t_apple = _ttr_test(author="2", corrected=p_tie)
    out_zebra_first = apply_cross_author_correction({"zebra": [t_zebra], "apple": [t_apple]})
    out_apple_first = apply_cross_author_correction({"apple": [t_apple], "zebra": [t_zebra]})
    assert (
        out_zebra_first["zebra"][0].cross_author_corrected_p
        == out_apple_first["zebra"][0].cross_author_corrected_p
    )
    assert (
        out_zebra_first["apple"][0].cross_author_corrected_p
        == out_apple_first["apple"][0].cross_author_corrected_p
    )
    assert out_zebra_first["zebra"][0].cross_author_corrected_p is not None
    assert out_zebra_first["zebra"][0].cross_author_correction_reason is None
