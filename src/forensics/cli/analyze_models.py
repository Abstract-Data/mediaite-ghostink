"""Shared dataclasses and path resolution for ``forensics analyze``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer

from forensics.analysis.orchestrator.mode import DEFAULT_ANALYSIS_MODE, AnalysisMode
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.paths import AnalysisArtifactPaths


@dataclass(frozen=True, slots=True)
class AnalyzeContext:
    """Shared paths/settings/slug for analyze stage runners."""

    db_path: Path
    settings: ForensicsSettings
    paths: AnalysisArtifactPaths
    author_slug: str | None
    max_workers: int | None = None
    compare_pair: tuple[str, str] | None = None
    analysis_mode: AnalysisMode = DEFAULT_ANALYSIS_MODE

    @classmethod
    def build(
        cls,
        db_path: Path,
        settings: ForensicsSettings,
        *,
        root: Path,
        author: str | None,
        max_workers: int | None = None,
        compare_pair: tuple[str, str] | None = None,
        analysis_mode: AnalysisMode = DEFAULT_ANALYSIS_MODE,
    ) -> AnalyzeContext:
        return cls(
            db_path=db_path,
            settings=settings,
            paths=AnalysisArtifactPaths.from_project(root, db_path),
            author_slug=author,
            max_workers=max_workers,
            compare_pair=compare_pair,
            analysis_mode=analysis_mode,
        )

    @property
    def root(self) -> Path:
        return self.paths.project_root


@dataclass(frozen=True, slots=True)
class AnalyzeSubcommandPaths:
    """Resolved settings and artifact paths for nested ``analyze`` commands."""

    settings: ForensicsSettings
    project_root: Path
    db_path: Path
    paths: AnalysisArtifactPaths
    features_dir: Path
    analysis_dir: Path


def resolve_analyze_subcommand_context(
    *,
    features_dir: Path | None,
) -> AnalyzeSubcommandPaths:
    """Shared preamble for ``section-profile`` / ``section-contrast`` (P3-DRY-007)."""
    settings = get_settings()
    project_root = get_project_root()
    db_path = project_root / DEFAULT_DB_RELATIVE
    paths = AnalysisArtifactPaths.from_project(project_root, db_path)
    feat_dir = features_dir if features_dir is not None else paths.features_dir
    return AnalyzeSubcommandPaths(
        settings=settings,
        project_root=project_root,
        db_path=db_path,
        paths=paths,
        features_dir=feat_dir,
        analysis_dir=paths.analysis_dir,
    )


@dataclass(frozen=True, slots=True)
class AnalyzeStageFlags:
    """Stage toggles grouped for dispatch."""

    changepoint: bool = False
    timeseries: bool = False
    drift: bool = False
    convergence: bool = False
    compare: bool = False
    ai_baseline: bool = False
    parallel_authors: bool = False


@dataclass(frozen=True, slots=True)
class AnalyzeBaselineParams:
    """AI baseline options grouped for dispatch."""

    skip_generation: bool = False
    baseline_model: str | None = None
    articles_per_cell: int | None = None


@dataclass(frozen=True, slots=True)
class AnalyzeCustodyParams:
    """Chain-of-custody CLI overrides (None = use ``config.toml``)."""

    verify_corpus: bool | None = None
    verify_raw_archives: bool | None = None
    log_all_generations: bool | None = None


@dataclass(frozen=True, slots=True)
class AnalyzeRequest:
    """Parameters for :func:`forensics.cli.analyze.run_analyze`."""

    stages: AnalyzeStageFlags = field(default_factory=AnalyzeStageFlags)
    baseline: AnalyzeBaselineParams = field(default_factory=AnalyzeBaselineParams)
    custody: AnalyzeCustodyParams = field(default_factory=AnalyzeCustodyParams)
    author: str | None = None
    include_advertorial: bool = False
    residualize_sections: bool = False
    include_shared_bylines: bool = False
    max_workers: int | None = None
    compare_pair: tuple[str, str] | None = None
    analysis_mode: AnalysisMode = DEFAULT_ANALYSIS_MODE
    typer_context: typer.Context | None = None

    @property
    def stage_flags(self) -> AnalyzeStageFlags:
        return self.stages

    @property
    def baseline_params(self) -> AnalyzeBaselineParams:
        return self.baseline

    @property
    def changepoint(self) -> bool:
        return self.stages.changepoint

    @property
    def timeseries(self) -> bool:
        return self.stages.timeseries

    @property
    def drift(self) -> bool:
        return self.stages.drift

    @property
    def convergence(self) -> bool:
        return self.stages.convergence

    @property
    def compare(self) -> bool:
        return self.stages.compare

    @property
    def ai_baseline(self) -> bool:
        return self.stages.ai_baseline

    @property
    def parallel_authors(self) -> bool:
        return self.stages.parallel_authors

    @property
    def skip_generation(self) -> bool:
        return self.baseline.skip_generation

    @property
    def baseline_model(self) -> str | None:
        return self.baseline.baseline_model

    @property
    def articles_per_cell(self) -> int | None:
        return self.baseline.articles_per_cell

    @property
    def verify_corpus(self) -> bool | None:
        return self.custody.verify_corpus

    @property
    def verify_raw_archives(self) -> bool | None:
        return self.custody.verify_raw_archives

    @property
    def log_all_generations(self) -> bool | None:
        return self.custody.log_all_generations
