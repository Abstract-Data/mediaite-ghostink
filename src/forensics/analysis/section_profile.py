"""Section-level descriptive report — newsroom-wide diagnostic (Phase 15 J3).

Produces the empirical evidence used to gate Phase 15 J5 (section-residualized
change-points). For each section that meets the retention thresholds, computes:

1. Centroid: mean vector of numeric stylometric features across every article
   in the section, newsroom-wide. Persisted as
   ``data/analysis/section_centroids.json``.
2. Inter-section cosine distance matrix: N×N matrix of cosine distances
   between section centroids. Persisted as
   ``data/analysis/section_distance_matrix.json`` plus a CSV mirror.
3. Per-feature Kruskal–Wallis ranking: omnibus test for whether the section
   grouping explains variance in each feature. ``statsmodels.MANOVA`` would
   be the textbook tool here but ``statsmodels`` is not in
   ``pyproject.toml``; per-feature Kruskal–Wallis (non-parametric, no
   distributional assumption) is the documented fallback. Persisted as
   ``data/analysis/section_feature_ranking.json``.

The human-readable summary lands at ``data/analysis/section_profile_report.md``
and includes the **J5 gate verdict** (PASS/FAIL/BORDERLINE) computed from:

* gate criterion 1: ≥ 3 feature families with omnibus p < 0.01
* gate criterion 2: max off-diagonal cosine distance > 0.3

Both criteria must hold for PASS. Exactly one → BORDERLINE (default-disable
J5 with the borderline note). Neither → FAIL (skip J5 entirely).

Retention thresholds (per section):

* ≥ ``settings.analysis.section_min_articles`` (default 50)
* ≥ 30 articles authored by ≥ 2 distinct authors (prevents one prolific
  author from defining a "section")
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import polars as pl
from scipy import stats

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.analysis.feature_families import family_for
from forensics.storage.json_io import write_json_artifact, write_text_atomic
from forensics.utils.url import section_from_url

if TYPE_CHECKING:
    from forensics.config.settings import ForensicsSettings

logger = logging.getLogger(__name__)

# Quantified J5 gate constants (locked here so callers + tests share one source).
GATE_MIN_SIGNIFICANT_FAMILIES: int = 3
GATE_OMNIBUS_ALPHA: float = 0.01
GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE: float = 0.3
TOP_K_FEATURES: int = 10
MIN_DISTINCT_AUTHORS: int = 2
MIN_AUTHORED_ARTICLES_THRESHOLD: int = 30

GateVerdict = Literal["PASS", "BORDERLINE", "FAIL", "DEGENERATE"]


@dataclass(frozen=True, slots=True)
class SectionProfileArtifacts:
    """Filesystem locations written by :func:`run_section_profile`."""

    centroids_json: Path
    distance_matrix_json: Path
    distance_matrix_csv: Path
    feature_ranking_json: Path
    report_md: Path


@dataclass(frozen=True, slots=True)
class SectionProfileResult:
    """In-memory return value mirroring the on-disk artifacts."""

    sections: list[str]
    centroids: dict[str, dict[str, float]]
    distance_matrix: list[list[float]]
    feature_ranking: list[dict[str, object]]
    gate_verdict: GateVerdict
    significant_families: list[str]
    max_off_diagonal_distance: float
    artifacts: SectionProfileArtifacts | None
    skipped_sections: dict[str, str]


def _section_artifact_paths(analysis_dir: Path) -> SectionProfileArtifacts:
    return SectionProfileArtifacts(
        centroids_json=analysis_dir / "section_centroids.json",
        distance_matrix_json=analysis_dir / "section_distance_matrix.json",
        distance_matrix_csv=analysis_dir / "section_distance_matrix.csv",
        feature_ranking_json=analysis_dir / "section_feature_ranking.json",
        report_md=analysis_dir / "section_profile_report.md",
    )


def _ensure_section_column(df: pl.DataFrame) -> pl.DataFrame:
    """Return ``df`` guaranteed to have a non-null ``section`` column.

    J1 (Wave 2.1) is adding the persisted ``section`` column to feature
    parquets in parallel with this module. Until every parquet ships v2,
    derive on the fly from ``url`` so this stage is robust against either
    state of the corpus. An empty input frame is returned unchanged — Polars
    treats ``pl.lit(...)`` on an empty zero-column frame as a length-1
    broadcast, which would silently invent a phantom row.
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


def _feature_columns(df: pl.DataFrame) -> list[str]:
    """Numeric stylometric features present in ``df``.

    Falls back to the PELT registry order so the centroid keys are stable
    across runs (and across fixtures that include / exclude derived columns).
    """
    return [c for c in PELT_FEATURE_COLUMNS if c in df.columns]


def _retain_sections(
    df: pl.DataFrame,
    *,
    min_articles: int,
) -> tuple[list[str], dict[str, str]]:
    """Return (sections to keep, {section: skip reason}) per the J3 retention rule."""
    if "section" not in df.columns:
        return [], {}
    grouped = (
        df.group_by("section")
        .agg(
            pl.len().alias("n_articles"),
            (pl.col("author_id").n_unique() if "author_id" in df.columns else pl.lit(1)).alias(
                "n_authors"
            ),
        )
        .sort("section")
    )
    keep: list[str] = []
    skipped: dict[str, str] = {}
    for row in grouped.iter_rows(named=True):
        section = row["section"]
        n_articles = int(row["n_articles"])
        n_authors = int(row["n_authors"])
        if n_articles < min_articles:
            skipped[section] = f"n_articles={n_articles} < section_min_articles={min_articles}"
            continue
        if n_articles < MIN_AUTHORED_ARTICLES_THRESHOLD or n_authors < MIN_DISTINCT_AUTHORS:
            skipped[section] = (
                f"n_articles={n_articles} or n_authors={n_authors} below "
                f"({MIN_AUTHORED_ARTICLES_THRESHOLD} articles / "
                f"{MIN_DISTINCT_AUTHORS} authors)"
            )
            continue
        keep.append(section)
    return keep, skipped


def _section_centroids(
    df: pl.DataFrame,
    sections: list[str],
    feature_cols: list[str],
) -> dict[str, dict[str, float]]:
    centroids: dict[str, dict[str, float]] = {}
    for section in sections:
        sub = df.filter(pl.col("section") == section)
        means = sub.select([pl.col(c).cast(pl.Float64).mean().alias(c) for c in feature_cols]).row(
            0, named=True
        )
        # Drop NaN means (all-null feature columns) so cosine distance is defined.
        centroids[section] = {
            c: float(v) for c, v in means.items() if v is not None and not math.isnan(float(v))
        }
    return centroids


def _vector_for(centroid: dict[str, float], feature_cols: list[str]) -> np.ndarray:
    """Project centroid onto ``feature_cols`` order, filling missing with 0.0."""
    return np.array([centroid.get(c, 0.0) for c in feature_cols], dtype=float)


def _cosine_distance_matrix(
    sections: list[str],
    centroids: dict[str, dict[str, float]],
    feature_cols: list[str],
) -> np.ndarray:
    n = len(sections)
    matrix = np.zeros((n, n), dtype=float)
    if n == 0:
        return matrix
    vectors = np.stack([_vector_for(centroids[s], feature_cols) for s in sections])
    norms = np.linalg.norm(vectors, axis=1)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            denom = norms[i] * norms[j]
            if denom == 0.0:
                matrix[i, j] = 1.0
                continue
            sim = float(np.dot(vectors[i], vectors[j]) / denom)
            # Clip floating-point overshoot so distance stays in [0, 2].
            sim = max(-1.0, min(1.0, sim))
            matrix[i, j] = 1.0 - sim
    return matrix


def _max_off_diagonal(matrix: np.ndarray) -> float:
    if matrix.size == 0 or matrix.shape[0] < 2:
        return 0.0
    n = matrix.shape[0]
    mask = ~np.eye(n, dtype=bool)
    values = matrix[mask]
    if values.size == 0:
        return 0.0
    return float(values.max())


def _kruskal_per_feature(
    df: pl.DataFrame,
    sections: list[str],
    feature_cols: list[str],
) -> list[dict[str, object]]:
    """Kruskal–Wallis omnibus test per feature.

    ``eta_squared`` is the rank-biserial η² approximation
    ``(H - k + 1) / (n - k)`` (Tomczak & Tomczak, 2014) clamped to [0, 1].
    Features whose Kruskal call is undefined (e.g. all values identical
    within every section) get NaN p and 0.0 effect.
    """
    rankings: list[dict[str, object]] = []
    k = len(sections)
    if k < 2:
        return rankings
    section_filters = {s: df.filter(pl.col("section") == s) for s in sections}
    for feature in feature_cols:
        groups: list[np.ndarray] = []
        section_means: dict[str, float] = {}
        section_medians: dict[str, float] = {}
        total_n = 0
        for section in sections:
            sub = section_filters[section]
            values = sub.select(pl.col(feature).cast(pl.Float64)).to_series().drop_nulls()
            arr = values.to_numpy()
            arr = arr[np.isfinite(arr)]
            groups.append(arr)
            total_n += arr.size
            if arr.size == 0:
                section_means[section] = float("nan")
                section_medians[section] = float("nan")
            else:
                section_means[section] = float(arr.mean())
                section_medians[section] = float(np.median(arr))
        # Kruskal needs ≥ 2 non-empty groups AND ≥ 2 distinct values overall —
        # otherwise scipy raises and the omnibus is undefined.
        usable = [g for g in groups if g.size > 0]
        all_values_unique = np.unique(np.concatenate(usable)).size if len(usable) >= 1 else 0
        if len(usable) < 2 or all_values_unique < 2:
            rankings.append(
                {
                    "feature": feature,
                    "family": family_for(feature),
                    "h_statistic": float("nan"),
                    "p_value": float("nan"),
                    "eta_squared": 0.0,
                    "n_total": total_n,
                    "section_means": section_means,
                    "section_medians": section_medians,
                }
            )
            continue
        try:
            h_stat, p_value = stats.kruskal(*usable)
        except ValueError:
            h_stat, p_value = float("nan"), float("nan")
        if total_n - k > 0 and not np.isnan(h_stat):
            eta_sq = float(max(0.0, min(1.0, (h_stat - k + 1) / (total_n - k))))
        else:
            eta_sq = 0.0
        rankings.append(
            {
                "feature": feature,
                "family": family_for(feature),
                "h_statistic": float(h_stat) if not np.isnan(h_stat) else float("nan"),
                "p_value": float(p_value) if not np.isnan(p_value) else float("nan"),
                "eta_squared": eta_sq,
                "n_total": total_n,
                "section_means": section_means,
                "section_medians": section_medians,
            }
        )
    rankings.sort(
        key=lambda row: -1.0 if np.isnan(float(row["eta_squared"])) else -float(row["eta_squared"])
    )
    return rankings


def _families_with_significant_omnibus(
    rankings: list[dict[str, object]],
    *,
    alpha: float = GATE_OMNIBUS_ALPHA,
) -> list[str]:
    families: set[str] = set()
    for row in rankings:
        p_value = row.get("p_value")
        if p_value is None:
            continue
        try:
            p_float = float(p_value)
        except (TypeError, ValueError):
            continue
        if np.isnan(p_float):
            continue
        if p_float < alpha:
            family = str(row.get("family", "unknown"))
            if family != "unknown":
                families.add(family)
    return sorted(families)


def compute_gate_verdict(
    *,
    significant_families: list[str],
    max_off_diagonal: float,
    n_sections: int,
) -> GateVerdict:
    """Return the J5 gate verdict from the two quantified criteria.

    ``DEGENERATE`` indicates fewer than two retained sections (no
    inter-section contrast is possible). ``PASS`` = both criteria hold.
    ``BORDERLINE`` = exactly one. ``FAIL`` = neither.
    """
    if n_sections < 2:
        return "DEGENERATE"
    cond_families = len(significant_families) >= GATE_MIN_SIGNIFICANT_FAMILIES
    cond_distance = max_off_diagonal > GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE
    if cond_families and cond_distance:
        return "PASS"
    if cond_families or cond_distance:
        return "BORDERLINE"
    return "FAIL"


def _write_distance_matrix_csv(
    path: Path,
    sections: list[str],
    matrix: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["section", *sections])
        for i, section in enumerate(sections):
            writer.writerow([section, *(f"{matrix[i, j]:.6f}" for j in range(len(sections)))])


_VERDICT_GUIDANCE: dict[str, str] = {
    "PASS": "Both criteria hold — enable J5 (section-residualized change-points).",
    "BORDERLINE": (
        "Exactly one criterion holds — default-disable J5 and document the "
        "borderline finding in HANDOFF.md per the v0.4.0 gate spec."
    ),
    "FAIL": (
        "Neither criterion holds — sections are stylometrically "
        "indistinguishable for this outlet. Skip J5 entirely."
    ),
    "DEGENERATE": (
        "Fewer than two retained sections — no inter-section contrast is "
        "possible. Treat the corpus as section-homogeneous; do not enable J5."
    ),
}


def _verdict_section(
    verdict: GateVerdict,
    significant_families: list[str],
    max_off_diagonal: float,
) -> list[str]:
    return [
        "## J5 Gate Verdict",
        "",
        f"- Verdict: **{verdict}**",
        (
            f"- Significant feature families (p < {GATE_OMNIBUS_ALPHA}): "
            f"{len(significant_families)} ({', '.join(significant_families) or 'none'})"
        ),
        (
            f"- Max off-diagonal cosine distance: {max_off_diagonal:.4f} "
            f"(threshold > {GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE})"
        ),
        (
            f"- Criteria satisfied: families≥{GATE_MIN_SIGNIFICANT_FAMILIES}="
            f"{len(significant_families) >= GATE_MIN_SIGNIFICANT_FAMILIES}, "
            f"distance>{GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE}="
            f"{max_off_diagonal > GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE}"
        ),
        "",
    ]


def _retention_section(sections: list[str], skipped: dict[str, str]) -> list[str]:
    lines = ["## Retained Sections", ""]
    if sections:
        lines.extend(f"- `{section}`" for section in sections)
    else:
        lines.append("_No sections met retention thresholds._")
    if skipped:
        lines.extend(["", "### Skipped Sections", ""])
        lines.extend(f"- `{section}` — {reason}" for section, reason in sorted(skipped.items()))
    lines.append("")
    return lines


def _distance_matrix_section(sections: list[str], distance_matrix: np.ndarray) -> list[str]:
    lines = ["## Inter-section Cosine Distance Matrix", ""]
    if len(sections) < 2:
        lines.append("_Need ≥ 2 retained sections for a contrast matrix._")
        lines.append("")
        return lines
    lines.append("| section | " + " | ".join(sections) + " |")
    lines.append("| --- |" + " --- |" * len(sections))
    for i, section in enumerate(sections):
        cells = " | ".join(f"{distance_matrix[i, j]:.4f}" for j in range(len(sections)))
        lines.append(f"| {section} | {cells} |")
    lines.append("")
    return lines


def _format_p_value(p_value: object) -> str:
    if isinstance(p_value, float) and np.isnan(p_value):
        return "nan"
    return f"{float(p_value):.4g}"


def _ranking_section(rankings: list[dict[str, object]]) -> list[str]:
    lines = [f"## Top {TOP_K_FEATURES} Features by Effect (η²)", ""]
    if not rankings:
        lines.append("_No omnibus tests run (need ≥ 2 sections)._")
        lines.append("")
        return lines
    lines.append("| feature | family | η² | p-value | n |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in rankings[:TOP_K_FEATURES]:
        lines.append(
            f"| {row['feature']} | {row['family']} | "
            f"{float(row['eta_squared']):.4f} | {_format_p_value(row['p_value'])} | "
            f"{row['n_total']} |"
        )
    lines.append("")
    return lines


def _format_report_markdown(
    *,
    sections: list[str],
    skipped: dict[str, str],
    distance_matrix: np.ndarray,
    rankings: list[dict[str, object]],
    significant_families: list[str],
    max_off_diagonal: float,
    verdict: GateVerdict,
) -> str:
    lines: list[str] = [
        "# Section Profile Report",
        "",
        (
            "Newsroom-wide diagnostic (Phase 15 J3) — answers whether sections are "
            "stylometrically distinct enough to justify Phase 15 J5 "
            "(section-residualized change-points)."
        ),
        "",
    ]
    lines.extend(_verdict_section(verdict, significant_families, max_off_diagonal))
    lines.extend(_retention_section(sections, skipped))
    lines.extend(_distance_matrix_section(sections, distance_matrix))
    lines.extend(_ranking_section(rankings))
    lines.append("## J5 Gate Decision Guidance")
    lines.append("")
    lines.append(_VERDICT_GUIDANCE.get(verdict, _VERDICT_GUIDANCE["DEGENERATE"]))
    lines.append("")
    return "\n".join(lines)


def compute_section_profile(
    df: pl.DataFrame,
    *,
    section_min_articles: int,
) -> SectionProfileResult:
    """Pure compute: produce the result without writing artifacts.

    Splitting the on-disk side from the math keeps the unit-test surface
    small (synthetic frames in, ``SectionProfileResult`` out) and lets the
    CLI reuse the same engine.
    """
    df = _ensure_section_column(df)
    feature_cols = _feature_columns(df)
    sections, skipped = _retain_sections(df, min_articles=section_min_articles)
    centroids = _section_centroids(df, sections, feature_cols)
    distance_matrix = _cosine_distance_matrix(sections, centroids, feature_cols)
    rankings = _kruskal_per_feature(df, sections, feature_cols)
    significant_families = _families_with_significant_omnibus(rankings)
    max_off_diag = _max_off_diagonal(distance_matrix)
    verdict = compute_gate_verdict(
        significant_families=significant_families,
        max_off_diagonal=max_off_diag,
        n_sections=len(sections),
    )
    return SectionProfileResult(
        sections=sections,
        centroids=centroids,
        distance_matrix=distance_matrix.tolist(),
        feature_ranking=rankings,
        gate_verdict=verdict,
        significant_families=significant_families,
        max_off_diagonal_distance=max_off_diag,
        artifacts=None,
        skipped_sections=skipped,
    )


def _load_corpus_frame(features_dir: Path) -> pl.DataFrame:
    """Concatenate every per-author feature parquet under ``features_dir``."""
    parquets = sorted(
        p for p in features_dir.glob("*.parquet") if p.parent.name != "_pre_phase15_backup"
    )
    if not parquets:
        return pl.DataFrame()
    frames: list[pl.DataFrame] = []
    for path in parquets:
        try:
            frames.append(pl.read_parquet(path))
        except (pl.exceptions.ComputeError, OSError) as exc:
            logger.warning("section-profile: skipping unreadable parquet %s (%s)", path, exc)
    if not frames:
        return pl.DataFrame()
    # ``how='diagonal'`` tolerates per-author column drift (e.g. different
    # optional features) without forcing a schema migration.
    return pl.concat(frames, how="diagonal_relaxed")


def write_section_profile(
    result: SectionProfileResult,
    analysis_dir: Path,
    *,
    report_path: Path | None = None,
) -> SectionProfileArtifacts:
    """Write all artifacts described in the module docstring."""
    artifacts = _section_artifact_paths(analysis_dir)
    if report_path is not None:
        artifacts = replace(artifacts, report_md=report_path)
    distance_matrix = np.asarray(result.distance_matrix, dtype=float)
    write_json_artifact(artifacts.centroids_json, result.centroids)
    write_json_artifact(
        artifacts.distance_matrix_json,
        {
            "sections": result.sections,
            "matrix": result.distance_matrix,
            "max_off_diagonal_distance": result.max_off_diagonal_distance,
        },
    )
    _write_distance_matrix_csv(artifacts.distance_matrix_csv, result.sections, distance_matrix)
    write_json_artifact(
        artifacts.feature_ranking_json,
        {
            "ranking": result.feature_ranking,
            "significant_families": result.significant_families,
            "gate_verdict": result.gate_verdict,
            "skipped_sections": result.skipped_sections,
        },
    )
    report_text = _format_report_markdown(
        sections=result.sections,
        skipped=result.skipped_sections,
        distance_matrix=distance_matrix,
        rankings=result.feature_ranking,
        significant_families=result.significant_families,
        max_off_diagonal=result.max_off_diagonal_distance,
        verdict=result.gate_verdict,
    )
    write_text_atomic(artifacts.report_md, report_text)
    return artifacts


def run_section_profile(
    settings: ForensicsSettings,
    *,
    features_dir: Path,
    analysis_dir: Path,
    report_path: Path | None = None,
) -> SectionProfileResult:
    """Top-level orchestrator wired by the ``analyze section-profile`` CLI.

    Walks every feature parquet under ``features_dir``, runs
    :func:`compute_section_profile`, persists the artifacts, and returns
    the in-memory result so the CLI can echo the gate verdict.
    """
    df = _load_corpus_frame(features_dir)
    if df.is_empty():
        logger.warning(
            "section-profile: no feature parquets found under %s — emitting empty report",
            features_dir,
        )
    result = compute_section_profile(
        df,
        section_min_articles=settings.analysis.section_min_articles,
    )
    artifacts = write_section_profile(result, analysis_dir, report_path=report_path)
    return replace(result, artifacts=artifacts)


__all__ = [
    "GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE",
    "GATE_MIN_SIGNIFICANT_FAMILIES",
    "GATE_OMNIBUS_ALPHA",
    "MIN_AUTHORED_ARTICLES_THRESHOLD",
    "MIN_DISTINCT_AUTHORS",
    "SectionProfileArtifacts",
    "SectionProfileResult",
    "compute_gate_verdict",
    "compute_section_profile",
    "run_section_profile",
    "write_section_profile",
]
