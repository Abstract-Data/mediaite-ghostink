"""Bundled filesystem locations for analysis, drift, and comparison stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forensics.config import DEFAULT_DB_RELATIVE


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

    def combined_umap_json(self) -> Path:
        return self.analysis_dir / "combined_umap.json"

    def ai_baseline_embeddings_dir(self, author_slug: str) -> Path:
        """Directory of per-article ``.npy`` vectors for synthetic AI baseline (Phase 10)."""
        return self.project_root / "data" / "ai_baseline" / author_slug / "embeddings"

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
