"""Per-author section-contrast tests (Phase 15 J6).

For each author with at least two sections each represented by at least
``MIN_SECTION_ARTICLES`` articles, run pairwise Welch + Mann-Whitney tests on
every PELT feature between the author's section samples. Apply per-family
Benjamini-Hochberg correction (re-using
:func:`forensics.analysis.statistics.apply_correction_grouped` from Phase 15
C2) and emit a JSON artifact at ``data/analysis/<slug>_section_contrast.json``.

Per-author diagnostic question: *does this author write opinion and politics
in measurably different registers?* An author with significant contrasts is
one for whom Phase A-C change-points should be interpreted with section-mix
in mind; an author with no significant contrasts is one for whom pooled
analysis was safe all along.

Edge cases (handled here, not in callers):

* **Single qualifying pair** — BH correction is still valid with a smaller
  per-family denominator. Emitted as one entry in ``pairs``.
* **No qualifying pairs** (< 2 sections meeting the article bar) — the
  artifact carries ``disposition: "insufficient_section_volume"`` and an
  empty ``pairs`` list. Downstream consumers render "N/A" rather than
  raising.
* **All features pass** in any single pair — emit a WARNING. An author who
  writes two sections in wholly different registers on every feature is
  suspicious and warrants a spot-check.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Literal

import numpy as np
import polars as pl
from scipy import stats

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.analysis.feature_families import family_for
from forensics.analysis.statistics import apply_correction_grouped
from forensics.models.analysis import HypothesisTest
from forensics.storage.json_io import write_json_artifact
from forensics.utils.url import section_from_url

__all__ = [
    "ALL_FEATURES_PASS_WARNING",
    "MIN_SECTION_ARTICLES",
    "SectionContrastPair",
    "SectionContrastResult",
    "compute_section_contrast",
    "section_contrast_artifact_path",
    "write_section_contrast_artifact",
]

logger = logging.getLogger(__name__)

# Per-section minimum article bar — matches the spec (≥ 30 per section).
MIN_SECTION_ARTICLES: int = 30

# Pinned WARNING template so the regression-pin test can match exactly.
ALL_FEATURES_PASS_WARNING: str = (
    "section_contrast: author=%s pair=(%s, %s) all %d features passed BH; "
    "spot-check this author — wholly different registers on every feature is suspicious."
)

Disposition = Literal["ok", "insufficient_section_volume"]


@dataclass(frozen=True, slots=True)
class SectionContrastPair:
    """One pairwise section contrast for a single author.

    ``significant_features_by_family`` maps each feature family to the sorted
    list of features that survived per-family BH at the configured alpha.
    Families with no surviving features are omitted from the dict (so an
    empty dict means "no significant contrast in this pair").
    """

    section_a: str
    section_b: str
    n_a: int
    n_b: int
    significant_features_by_family: dict[str, list[str]]

    def to_dict(self) -> dict[str, object]:
        return {
            "section_a": self.section_a,
            "section_b": self.section_b,
            "n_a": int(self.n_a),
            "n_b": int(self.n_b),
            "significant_features_by_family": {
                family: list(features)
                for family, features in sorted(self.significant_features_by_family.items())
            },
        }


@dataclass(frozen=True, slots=True)
class SectionContrastResult:
    """Per-author result; ``disposition`` flags the empty-pairs short-circuit."""

    author_id: str
    pairs: list[SectionContrastPair]
    disposition: Disposition

    def to_dict(self) -> dict[str, object]:
        return {
            "author_id": self.author_id,
            "disposition": self.disposition,
            "pairs": [pair.to_dict() for pair in self.pairs],
        }


def _ensure_section_column(df: pl.DataFrame) -> pl.DataFrame:
    """Return ``df`` guaranteed to have a non-null ``section`` column.

    Mirrors :func:`forensics.analysis.section_profile._ensure_section_column`
    so callers can pass either a feature parquet (post-J1) or a frame with
    only ``url`` (pre-J1) and get the same behaviour.
    """
    if df.is_empty():
        return df
    if "section" in df.columns:
        return df.with_columns(pl.col("section").fill_null("unknown"))
    if "url" in df.columns:
        return df.with_columns(
            pl.col("url").map_elements(section_from_url, return_dtype=pl.Utf8).alias("section")
        )
    return df.with_columns(pl.lit("unknown").alias("section"))


def _qualifying_sections(df: pl.DataFrame) -> list[str]:
    """Sections held by this author with ≥ ``MIN_SECTION_ARTICLES`` articles, sorted."""
    if df.is_empty() or "section" not in df.columns:
        return []
    counts = (
        df.group_by("section")
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") >= MIN_SECTION_ARTICLES)
        .sort("section")
    )
    return [row["section"] for row in counts.iter_rows(named=True)]


def _feature_columns(df: pl.DataFrame) -> list[str]:
    """Numeric stylometric features present in ``df`` in PELT-registry order."""
    return [c for c in PELT_FEATURE_COLUMNS if c in df.columns]


def _safe_two_sided_pvalue(value: float) -> float:
    """Clamp a raw p-value into ``[0, 1]``, defaulting NaN/inf to 1.0."""
    p = float(value)
    if not np.isfinite(p):
        return 1.0
    return min(1.0, max(0.0, p))


def _build_test_row(
    *,
    prefix: str,
    section_a: str,
    section_b: str,
    feature: str,
    author_id: str,
    p_value: float,
) -> HypothesisTest:
    """Construct a HypothesisTest row for a section-pair test.

    ``effect_size_cohens_d`` and ``confidence_interval_95`` are not consumed
    by the J6 artifact (only feature-level significance is rolled up by
    family) so they're left at zero — saves a per-feature bootstrap.
    """
    safe_p = _safe_two_sided_pvalue(p_value)
    return HypothesisTest(
        test_name=f"{prefix}_{section_a}_vs_{section_b}_{feature}",
        feature_name=feature,
        author_id=author_id,
        raw_p_value=safe_p,
        corrected_p_value=safe_p,
        effect_size_cohens_d=0.0,
        confidence_interval_95=(0.0, 0.0),
        significant=False,
    )


def _pair_tests(
    df: pl.DataFrame,
    *,
    section_a: str,
    section_b: str,
    feature_cols: list[str],
    author_id: str,
) -> list[HypothesisTest]:
    """Welch + Mann-Whitney per feature for one (section_a, section_b) pair.

    Skips features whose split has fewer than two finite values per side —
    the skip yields no test rows for that feature in this pair, so an
    untested hypothesis cannot inflate the BH denominator.
    """
    a_df = df.filter(pl.col("section") == section_a)
    b_df = df.filter(pl.col("section") == section_b)
    out: list[HypothesisTest] = []
    for feature in feature_cols:
        a_vals = a_df.select(pl.col(feature).cast(pl.Float64)).to_series().to_numpy()
        b_vals = b_df.select(pl.col(feature).cast(pl.Float64)).to_series().to_numpy()
        a_clean = a_vals[np.isfinite(a_vals)]
        b_clean = b_vals[np.isfinite(b_vals)]
        if a_clean.size < 2 or b_clean.size < 2:
            continue
        try:
            _t, p_welch = stats.ttest_ind(a_clean, b_clean, equal_var=False)
        except (ValueError, FloatingPointError):
            p_welch = 1.0
        # Both sides identical → MW raises; treat as no contrast (p=1.0).
        try:
            _u, p_mw = stats.mannwhitneyu(a_clean, b_clean, alternative="two-sided")
        except ValueError:
            p_mw = 1.0
        out.append(
            _build_test_row(
                prefix="welch_t",
                section_a=section_a,
                section_b=section_b,
                feature=feature,
                author_id=author_id,
                p_value=float(p_welch),
            )
        )
        out.append(
            _build_test_row(
                prefix="mann_whitney",
                section_a=section_a,
                section_b=section_b,
                feature=feature,
                author_id=author_id,
                p_value=float(p_mw),
            )
        )
    return out


def _significant_features_by_family(
    corrected_tests: list[HypothesisTest],
    feature_cols: list[str],
) -> dict[str, list[str]]:
    """Roll corrected tests into ``{family: sorted feature names}``.

    A feature is considered significant for the pair if **either** the Welch
    or Mann-Whitney corrected p-value crosses the alpha gate. Using the
    union mirrors the spec ("significant on this feature") — readers want to
    know whether the feature distinguished the two sections, not which
    specific test won.
    """
    sig_features: set[str] = set()
    for test in corrected_tests:
        if test.significant:
            sig_features.add(test.feature_name)
    grouped: dict[str, list[str]] = defaultdict(list)
    for feature in feature_cols:
        if feature in sig_features:
            grouped[family_for(feature)].append(feature)
    return {family: sorted(features) for family, features in sorted(grouped.items())}


def compute_section_contrast(
    df: pl.DataFrame,
    *,
    author_id: str,
    alpha: float = 0.05,
    bh_method: str = "benjamini_hochberg",
) -> SectionContrastResult:
    """Pure-compute entry point: returns the result without writing artifacts.

    Mirrors the J3 / J4 split — keeps the unit-test surface small (synthetic
    frame in, dataclass out) and lets callers decide whether to persist.
    """
    df = _ensure_section_column(df)
    sections = _qualifying_sections(df)
    if len(sections) < 2:
        return SectionContrastResult(
            author_id=author_id,
            pairs=[],
            disposition="insufficient_section_volume",
        )
    feature_cols = _feature_columns(df)
    pairs: list[SectionContrastPair] = []
    n_total_features = len(feature_cols)
    for section_a, section_b in combinations(sections, 2):
        n_a = int(df.filter(pl.col("section") == section_a).height)
        n_b = int(df.filter(pl.col("section") == section_b).height)
        tests = _pair_tests(
            df,
            section_a=section_a,
            section_b=section_b,
            feature_cols=feature_cols,
            author_id=author_id,
        )
        # Per-family BH using the C2 helper. Singleton families return raw
        # p-values unchanged (BH no-op when n=1) — mathematically correct.
        corrected = apply_correction_grouped(
            tests,
            group_key=lambda t: family_for(t.feature_name),
            method=bh_method,
            alpha=alpha,
        )
        sig_by_family = _significant_features_by_family(corrected, feature_cols)
        n_sig_features = sum(len(features) for features in sig_by_family.values())
        if n_total_features > 0 and n_sig_features == n_total_features:
            logger.warning(
                ALL_FEATURES_PASS_WARNING,
                author_id,
                section_a,
                section_b,
                n_total_features,
            )
        pairs.append(
            SectionContrastPair(
                section_a=section_a,
                section_b=section_b,
                n_a=n_a,
                n_b=n_b,
                significant_features_by_family=sig_by_family,
            )
        )
    return SectionContrastResult(
        author_id=author_id,
        pairs=pairs,
        disposition="ok",
    )


def section_contrast_artifact_path(analysis_dir: Path, author_slug: str) -> Path:
    """Canonical artifact path for the per-author section-contrast JSON."""
    return analysis_dir / f"{author_slug}_section_contrast.json"


def write_section_contrast_artifact(
    result: SectionContrastResult,
    artifact_path: Path,
) -> None:
    """Atomically write ``result`` as canonical JSON.

    Uses :func:`write_json_artifact` (atomic rename, ``sort_keys`` is not
    set there but we order pairs/families/features deterministically
    upstream so the rendered bytes are stable for a fixed fixture).
    """
    write_json_artifact(artifact_path, result.to_dict())


def compute_and_write_section_contrast(
    df: pl.DataFrame,
    *,
    author_id: str,
    author_slug: str,
    analysis_dir: Path,
    alpha: float = 0.05,
    bh_method: str = "benjamini_hochberg",
) -> tuple[SectionContrastResult, Path]:
    """Convenience wrapper used by the CLI: compute, persist, return both."""
    result = compute_section_contrast(
        df,
        author_id=author_id,
        alpha=alpha,
        bh_method=bh_method,
    )
    path = section_contrast_artifact_path(analysis_dir, author_slug)
    write_section_contrast_artifact(result, path)
    return result, path
