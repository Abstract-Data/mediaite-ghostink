"""Bundled filesystem locations for analysis, drift, and comparison stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AnalysisArtifactPaths:
    """Paths that travel together through orchestration and comparison."""

    project_root: Path
    db_path: Path
    features_dir: Path
    embeddings_dir: Path
    analysis_dir: Path

    @classmethod
    def from_project(cls, project_root: Path, db_path: Path | None = None) -> AnalysisArtifactPaths:
        """Default layout under ``project_root/data``."""
        return cls.from_layout(
            project_root,
            db_path or project_root / "data" / "articles.db",
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
