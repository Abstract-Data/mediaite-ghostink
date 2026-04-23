"""Blind survey orchestrator — run the full pipeline across every qualified author.

Phase 12 §1c. Produces per-author analysis results ranked by composite AI-adoption
signal, with a JSON checkpoint after each author so long runs can resume after
interruption.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.orchestrator import run_full_analysis
from forensics.config.settings import ForensicsSettings
from forensics.features.pipeline import extract_all_features
from forensics.models.analysis import AnalysisResult
from forensics.storage.json_io import write_json_artifact
from forensics.survey.qualification import (
    QualificationCriteria,
    QualifiedAuthor,
    qualify_authors,
)
from forensics.survey.scoring import (
    SignalStrength,
    SurveyScore,
    compute_composite_score,
    identify_natural_controls,
    validate_against_controls,
)

logger = logging.getLogger(__name__)


@dataclass
class SurveyResult:
    """Complete survey output for a single author."""

    author_slug: str
    author_name: str
    qualification: QualifiedAuthor
    analysis: AnalysisResult | None = None
    score: SurveyScore | None = None
    error: str | None = None


@dataclass
class SurveyReport:
    """Top-level survey run metadata and ranked results."""

    run_id: str = field(default_factory=lambda: str(uuid4()))
    run_timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    config_hash: str = ""
    total_authors_discovered: int = 0
    total_qualified: int = 0
    total_disqualified: int = 0
    results: list[SurveyResult] = field(default_factory=list)
    natural_controls: list[str] = field(default_factory=list)
    run_dir: Path | None = None


def _compute_config_hash(settings: ForensicsSettings) -> str:
    payload = json.dumps(settings.analysis.model_dump(mode="json"), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _run_dir_for(project_root: Path, run_id: str) -> Path:
    return project_root / "data" / "survey" / f"run_{run_id}"


def _checkpoint_path(run_dir: Path) -> Path:
    return run_dir / "checkpoint.json"


def _load_checkpoint(run_dir: Path) -> set[str]:
    path = _checkpoint_path(run_dir)
    if not path.is_file():
        logger.warning("survey: checkpoint not found at %s", path)
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("survey: could not parse checkpoint %s (%s)", path, exc)
        return set()
    return set(data.get("completed_slugs", []))


def _write_checkpoint(report: SurveyReport) -> None:
    if report.run_dir is None:
        return
    completed = [r.author_slug for r in report.results if r.analysis is not None]
    payload = {
        "run_id": report.run_id,
        "run_timestamp": report.run_timestamp,
        "config_hash": report.config_hash,
        "updated_at": datetime.now(UTC).isoformat(),
        "completed_slugs": completed,
    }
    write_json_artifact(_checkpoint_path(report.run_dir), payload)


def _write_survey_results(report: SurveyReport) -> None:
    if report.run_dir is None:
        return

    rankings: list[dict[str, Any]] = []
    for rank, result in enumerate(report.results, start=1):
        rankings.append(
            {
                "rank": rank,
                "author_slug": result.author_slug,
                "author_name": result.author_name,
                "composite_score": result.score.composite if result.score else None,
                "signal_strength": (result.score.strength.value if result.score else "error"),
                "total_articles": result.qualification.total_articles,
                "convergence_windows": (
                    len(result.analysis.convergence_windows) if result.analysis else 0
                ),
                "error": result.error,
            }
        )

    output: dict[str, Any] = {
        "run_id": report.run_id,
        "run_timestamp": report.run_timestamp,
        "config_hash": report.config_hash,
        "summary": {
            "total_discovered": report.total_authors_discovered,
            "total_qualified": report.total_qualified,
            "total_disqualified": report.total_disqualified,
            "total_processed": len(report.results),
            "total_errors": sum(1 for r in report.results if r.error),
            "natural_control_count": len(report.natural_controls),
        },
        "natural_controls": report.natural_controls,
        "rankings": rankings,
    }

    write_json_artifact(report.run_dir / "survey_results.json", output)


def _rank_results(report: SurveyReport) -> None:
    report.results.sort(
        key=lambda r: r.score.composite if r.score else -1.0,
        reverse=True,
    )


async def _process_author(
    qa: QualifiedAuthor,
    *,
    db_path: Path,
    settings: ForensicsSettings,
    project_root: Path,
) -> SurveyResult:
    slug = qa.author.slug
    result = SurveyResult(
        author_slug=slug,
        author_name=qa.author.name,
        qualification=qa,
    )

    try:
        extract_all_features(
            db_path,
            settings,
            author_slug=slug,
            project_root=project_root,
        )

        paths = AnalysisArtifactPaths.from_project(project_root, db_path)
        analysis_map = await run_full_analysis(
            paths,
            settings,
            author_slug=slug,
        )
        analysis = analysis_map.get(slug)
        result.analysis = analysis
        if analysis is not None:
            result.score = compute_composite_score(analysis, qa)
    except Exception as exc:  # noqa: BLE001
        logger.error("survey: failed on %s (%s)", slug, exc, exc_info=True)
        result.error = str(exc)

    return result


async def run_survey(
    settings: ForensicsSettings,
    *,
    project_root: Path | None = None,
    db_path: Path | None = None,
    dry_run: bool = False,
    resume: str | None = None,
    skip_scrape: bool = False,
    author: str | None = None,
    criteria: QualificationCriteria | None = None,
    post_year_min: int | None = None,
    post_year_max: int | None = None,
) -> SurveyReport:
    """Execute the blind survey pipeline.

    Phases:
    1. Optional scrape (``skip_scrape=False``) — discovery + metadata + fetch for
       every author on the manifest via :func:`forensics.cli.scrape.dispatch_scrape`.
    2. Qualify all discovered authors against :class:`QualificationCriteria`.
    3. For each qualifying author, extract features, run full analysis, and
       compute the composite AI-adoption score.
    4. Identify the natural control cohort and write survey_results.json.

    Args:
        settings: Forensics settings loaded via :func:`forensics.config.get_settings`.
        project_root: Project root directory; defaults to ``get_project_root()``.
        db_path: Articles SQLite path; defaults to ``<project_root>/data/articles.db``.
        dry_run: If ``True``, list qualified authors and return without running
            scrape/extract/analyze.
        resume: Optional run id to resume; authors already in the checkpoint are
            skipped.
        skip_scrape: If ``True``, reuse the existing corpus; do not call the
            scraper.
        author: Optional author slug — survey only this author (debugging).
        criteria: Optional qualification override; defaults to
            ``QualificationCriteria.from_settings(settings.survey)``.
        post_year_min: Optional inclusive year lower bound for the scrape step
            (with ``post_year_max``); overrides ``settings.scraping`` when set.
        post_year_max: Optional inclusive year upper bound for the scrape step.
    """
    from forensics.config import get_project_root

    root = project_root if project_root is not None else get_project_root()
    db = db_path if db_path is not None else root / "data" / "articles.db"

    run_id = resume or str(uuid4())
    run_dir = _run_dir_for(root, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    report = SurveyReport(
        run_id=run_id,
        config_hash=_compute_config_hash(settings),
        run_dir=run_dir,
    )

    completed_slugs: set[str] = set()
    if resume:
        completed_slugs = _load_checkpoint(run_dir)
        logger.info(
            "survey: resuming run %s (%d authors already completed)",
            run_id,
            len(completed_slugs),
        )

    effective_criteria = criteria or QualificationCriteria.from_settings(settings.survey)

    if not skip_scrape and not dry_run:
        # Survey mode uses the discovered manifest, not config.toml authors.
        from forensics.cli.scrape import dispatch_scrape

        logger.info("survey: running full scrape pipeline first (all authors)")
        rc = await dispatch_scrape(
            discover=False,
            metadata=False,
            fetch=False,
            dedup=False,
            archive=False,
            dry_run=False,
            force_refresh=False,
            all_authors=True,
            post_year_min=post_year_min,
            post_year_max=post_year_max,
        )
        if rc != 0:
            logger.error("survey: scrape failed with exit code %d", rc)
            report.results = []
            _write_checkpoint(report)
            _write_survey_results(report)
            return report

    qualified, disqualified = qualify_authors(db, effective_criteria)
    report.total_qualified = len(qualified)
    report.total_disqualified = len(disqualified)
    report.total_authors_discovered = len(qualified) + len(disqualified)

    if author:
        qualified = [q for q in qualified if q.author.slug == author]
        if not qualified:
            logger.error("survey: author %s not found among qualifying authors", author)
            _write_checkpoint(report)
            _write_survey_results(report)
            return report

    if dry_run:
        logger.info(
            "survey: dry-run complete — %d qualified, %d disqualified",
            len(qualified),
            len(disqualified),
        )
        # Record qualified authors on the report so callers can enumerate them
        # without re-querying the database.
        report.results = [
            SurveyResult(
                author_slug=qa.author.slug,
                author_name=qa.author.name,
                qualification=qa,
            )
            for qa in qualified
        ]
        _write_checkpoint(report)
        _write_survey_results(report)
        return report

    total = len(qualified)
    for idx, qa in enumerate(qualified, start=1):
        slug = qa.author.slug
        if slug in completed_slugs:
            logger.info("survey: [%d/%d] skipping %s (already completed)", idx, total, slug)
            continue

        logger.info(
            "survey: [%d/%d] processing %s (%d articles)",
            idx,
            total,
            slug,
            qa.total_articles,
        )

        result = await _process_author(
            qa,
            db_path=db,
            settings=settings,
            project_root=root,
        )
        report.results.append(result)
        _write_checkpoint(report)

    _rank_results(report)

    score_map: dict[str, SurveyScore] = {
        r.author_slug: r.score for r in report.results if r.score is not None
    }
    # Error entries — mark as ERROR so identify_natural_controls skips them.
    for r in report.results:
        if r.error is not None and r.author_slug not in score_map:
            score_map[r.author_slug] = SurveyScore(
                composite=-1.0,
                strength=SignalStrength.ERROR,
                pipeline_a_score=0.0,
                pipeline_b_score=0.0,
                pipeline_c_score=None,
                convergence_score=0.0,
                num_convergence_windows=0,
                strongest_window_ratio=0.0,
                max_effect_size=0.0,
                evidence_summary=r.error,
            )

    report.natural_controls = identify_natural_controls(score_map)
    validation = validate_against_controls(score_map, report.natural_controls)
    logger.info(
        "survey: complete — %d processed, %d errors, %d natural controls "
        "(mean composite=%.3f, max=%.3f)",
        len(report.results),
        sum(1 for r in report.results if r.error),
        validation.num_controls,
        validation.mean_composite,
        validation.max_composite,
    )

    _write_survey_results(report)
    return report
