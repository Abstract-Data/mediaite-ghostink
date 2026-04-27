"""Cross-stage path helpers and author resolution (RF-ARCH-001).

Re-exported from ``forensics.analysis.*`` for backward-compatible imports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from forensics.config import DEFAULT_DB_RELATIVE
from forensics.storage.parquet import load_feature_frame_sorted

if TYPE_CHECKING:
    from forensics.config.settings import ForensicsSettings
    from forensics.models.author import Author
    from forensics.storage.repository import Repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AnalysisArtifactPaths:
    """Paths that travel together through orchestration and comparison."""

    project_root: Path
    db_path: Path
    features_dir: Path
    embeddings_dir: Path
    analysis_dir: Path

    def features_parquet(self, author_slug: str) -> Path:
        return self.features_dir / f"{author_slug}.parquet"

    def changepoints_json(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_changepoints.json"

    def convergence_json(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_convergence.json"

    def convergence_components_json(self, author_slug: str) -> Path:
        """L-01 — per-window convergence component breakdown (JSON)."""
        return self.analysis_dir / f"{author_slug}_convergence_components.json"

    def imputation_stats_json(self, author_slug: str) -> Path:
        """L-05 — NaN / inf imputation counts prior to changepoint detection."""
        return self.analysis_dir / f"{author_slug}_imputation_stats.json"

    def result_json(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_result.json"

    def hypothesis_tests_json(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_hypothesis_tests.json"

    def drift_json(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_drift.json"

    def baseline_curve_json(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_baseline_curve.json"

    def centroids_npz(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_centroids.npz"

    def umap_json(self, author_slug: str) -> Path:
        return self.analysis_dir / f"{author_slug}_umap.json"

    def comparison_report_json(self) -> Path:
        return self.analysis_dir / "comparison_report.json"

    def run_metadata_json(self) -> Path:
        return self.analysis_dir / "run_metadata.json"

    @property
    def scrape_errors_path(self) -> Path:
        """Directory for ``scrape_errors.jsonl`` and auxiliary per-job error JSON."""
        return self.project_root / "data"

    def combined_umap_json(self) -> Path:
        return self.analysis_dir / "combined_umap.json"

    def sensitivity_dir(self, name: str) -> Path:
        return self.analysis_dir / "sensitivity" / name

    def with_analysis_dir(self, analysis_dir: Path) -> AnalysisArtifactPaths:
        return AnalysisArtifactPaths(
            project_root=self.project_root,
            db_path=self.db_path,
            features_dir=self.features_dir,
            embeddings_dir=self.embeddings_dir,
            analysis_dir=analysis_dir,
        )

    def ai_baseline_dir(self, author_slug: str) -> Path:
        """Root directory for one author's synthetic AI baseline artifacts."""
        return self.project_root / "data" / "ai_baseline" / author_slug

    def ai_baseline_embeddings_dir(self, author_slug: str) -> Path:
        """Directory of per-article ``.npy`` vectors for synthetic AI baseline (Phase 10)."""
        return self.ai_baseline_dir(author_slug) / "embeddings"

    @classmethod
    def from_project(cls, project_root: Path, db_path: Path | None = None) -> AnalysisArtifactPaths:
        """Default layout under ``project_root/data``."""
        resolved_db = db_path if db_path is not None else project_root / DEFAULT_DB_RELATIVE
        return cls.from_layout(
            project_root,
            resolved_db,
            project_root / "data" / "features",
            project_root / "data" / "embeddings",
        )

    @classmethod
    def from_layout(
        cls,
        project_root: Path,
        db_path: Path,
        features_dir: Path,
        embeddings_dir: Path,
        *,
        analysis_dir: Path | None = None,
    ) -> AnalysisArtifactPaths:
        return cls(
            project_root=project_root,
            db_path=db_path,
            features_dir=features_dir,
            embeddings_dir=embeddings_dir,
            analysis_dir=analysis_dir or project_root / "data" / "analysis",
        )


def intervals_overlap(
    a0: datetime | date,
    a1: datetime | date,
    b0: datetime | date,
    b1: datetime | date,
) -> bool:
    """Return True if closed intervals ``[a0, a1]`` and ``[b0, b1]`` intersect."""
    return a0 <= b1 and b0 <= a1


def closed_interval_contains(
    value: datetime | date,
    lo: datetime | date,
    hi: datetime | date,
) -> bool:
    """Return True if ``lo <= value <= hi`` for mutually orderable operands (e.g. dates)."""
    return lo <= value <= hi


def load_feature_frame_for_author(
    features_dir: Path,
    slug: str,
    author_id: str,
) -> pl.DataFrame | None:
    """Load ``{slug}.parquet`` filtered by ``author_id`` in the scan (P2-PERF-002)."""
    path = features_dir / f"{slug}.parquet"
    if not path.is_file():
        return None
    lf = load_feature_frame_sorted(path)
    dfc = lf.filter(pl.col("author_id") == author_id).collect()
    if dfc.is_empty():
        logger.warning(
            "No feature rows for author_id=%s in %s (slug=%s); loading full parquet "
            "as fallback — downstream code must filter by author_id.",
            author_id,
            path.name,
            slug,
        )
        dfc = lf.collect()
    return dfc


def resolve_author_rows(
    repo: Repository,
    settings: ForensicsSettings,
    *,
    author_slug: str | None,
) -> list[Author]:
    """DB :class:`Author` rows for config, optionally a single ``author_slug``."""
    if author_slug:
        au = repo.get_author_by_slug(author_slug)
        if au is None:
            msg = f"Unknown author slug: {author_slug}"
            raise ValueError(msg)
        return [au]
    by_slug = repo.get_authors_by_slugs(a.slug for a in settings.authors)
    rows: list[Author] = []
    for a in settings.authors:
        au = by_slug.get(a.slug)
        if au is not None:
            rows.append(au)
    return rows


__all__ = [
    "AnalysisArtifactPaths",
    "closed_interval_contains",
    "intervals_overlap",
    "load_feature_frame_for_author",
    "resolve_author_rows",
]
