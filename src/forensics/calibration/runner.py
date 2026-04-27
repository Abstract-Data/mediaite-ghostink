"""Calibration trials (splice vs negative), survey scoring, metrics JSON.

Output lives under ``data/calibration/``. Tests patch ``_load_author_articles``,
``_load_ai_articles``, and ``_run_trial_analysis``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.orchestrator import run_full_analysis
from forensics.calibration.synthetic import (
    SyntheticCorpus,
    build_negative_control,
    build_spliced_corpus,
)
from forensics.config.settings import DEFAULT_DB_RELATIVE, ForensicsSettings
from forensics.features.pipeline import extract_all_features
from forensics.models.analysis import AnalysisResult
from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import Repository, init_db
from forensics.survey.scoring import SignalStrength, compute_composite_score
from forensics.utils.datetime import utc_archive_stamp

logger = logging.getLogger(__name__)

# WEAK+ counts as a detection fire (NONE = no signal).
_FIRED_STRENGTHS = frozenset({SignalStrength.WEAK, SignalStrength.MODERATE, SignalStrength.STRONG})


@dataclass(frozen=True)
class CalibrationTrial:
    """One calibration trial result."""

    author_slug: str
    splice_date: date | None
    is_positive: bool
    detected: bool
    detection_date: date | None
    composite_score: float
    convergence_windows: int
    date_error_days: int | None


@dataclass(frozen=True)
class CalibrationReport:
    """Aggregate calibration metrics."""

    trials: list[CalibrationTrial]
    sensitivity: float
    specificity: float
    precision: float
    f1_score: float
    median_date_error_days: float | None
    report_path: Path | None = None


@dataclass(frozen=True)
class _TrialOutcome:
    """Outcome of a single extract+analyze invocation."""

    composite_score: float
    detected: bool
    detection_date: date | None
    convergence_windows: int


def compute_metrics(trials: list[CalibrationTrial]) -> dict[str, float | None]:
    """Compute sensitivity / specificity / precision / F1 / median date error.

    Exposed separately so unit tests can feed hand-crafted trial lists without
    invoking the analysis pipeline.
    """
    tp = sum(1 for t in trials if t.is_positive and t.detected)
    fn = sum(1 for t in trials if t.is_positive and not t.detected)
    tn = sum(1 for t in trials if not t.is_positive and not t.detected)
    fp = sum(1 for t in trials if not t.is_positive and t.detected)

    sensitivity = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    denom = precision + sensitivity
    f1 = (2 * precision * sensitivity / denom) if denom else 0.0

    date_errors = [t.date_error_days for t in trials if t.date_error_days is not None]
    if date_errors:
        median_err: float | None = float(np.median(date_errors))
    else:
        median_err = None

    return {
        "sensitivity": sensitivity,
        "specificity": specificity,
        "precision": precision,
        "f1_score": f1,
        "median_date_error_days": median_err,
    }


def _earliest_changepoint_date(analysis: AnalysisResult) -> date | None:
    if not analysis.change_points:
        return None
    earliest = min(cp.timestamp for cp in analysis.change_points)
    return earliest.date()


def _outcome_from_analysis(analysis: AnalysisResult | None) -> _TrialOutcome:
    if analysis is None:
        return _TrialOutcome(
            composite_score=0.0,
            detected=False,
            detection_date=None,
            convergence_windows=0,
        )
    score = compute_composite_score(analysis)
    return _TrialOutcome(
        composite_score=score.composite,
        detected=score.strength in _FIRED_STRENGTHS,
        detection_date=_earliest_changepoint_date(analysis),
        convergence_windows=len(analysis.convergence_windows),
    )


def _load_author_articles(db_path: Path, slug: str | None) -> tuple[Author, list[Article]]:
    """Return ``(author, articles)`` for the requested slug or the most prolific."""
    with Repository(db_path) as repo:
        authors = repo.all_authors()
        if slug:
            candidates = [a for a in authors if a.slug == slug]
            if not candidates:
                raise ValueError(f"author slug {slug!r} not found in {db_path}")
            target = candidates[0]
            return target, repo.get_articles_by_author(target.id)
        best: tuple[Author, list[Article]] | None = None
        for author in authors:
            articles = repo.get_articles_by_author(author.id)
            if best is None or len(articles) > len(best[1]):
                best = (author, articles)
        if best is None:
            raise ValueError(f"no authors found in {db_path}")
        return best


def _load_ai_articles(project_root: Path, author: Author) -> list[Article]:
    """Load Phase 10 AI baseline articles for this author, if any.

    Expects ``data/ai_baseline/<slug>/articles.json`` — a list of article
    payloads compatible with :class:`Article`. Returns ``[]`` if the file is
    missing so the runner can still operate in best-effort mode.
    """
    candidate = project_root / "data" / "ai_baseline" / author.slug / "articles.json"
    if not candidate.is_file():
        logger.warning("calibration: AI baseline not found at %s — using []", candidate)
        return []
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("calibration: failed to read %s (%s)", candidate, exc)
        return []
    return [Article.model_validate(item) for item in payload]


def _write_corpus_to_db(
    db_path: Path,
    author: Author,
    articles: list[Article],
) -> None:
    """Materialise a synthetic corpus into a fresh SQLite database."""
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(author)
        for art in articles:
            repo.upsert_article(art)


def _pick_splice_date(articles: list[Article], rng: np.random.Generator) -> date:
    """Pick a random splice date between the 30th and 70th percentile of dates."""
    dates = sorted(a.published_date.date() for a in articles)
    if len(dates) < 3:
        return dates[len(dates) // 2]
    lo_idx = int(len(dates) * 0.3)
    hi_idx = int(len(dates) * 0.7)
    idx = int(rng.integers(lo_idx, max(hi_idx, lo_idx + 1)))
    return dates[idx]


async def _run_trial_analysis(
    corpus: SyntheticCorpus,
    author: Author,
    *,
    settings: ForensicsSettings,
    project_root: Path,
    trial_root: Path,
) -> AnalysisResult | None:
    """Materialise the corpus, run extract_all_features + run_full_analysis.

    Returns the :class:`AnalysisResult` for the author or ``None`` if nothing
    could be produced. The trial is fully isolated under ``trial_root`` so
    concurrent trials do not trample each other.
    """
    # trial_root is created by Repository.__enter__ (db_path.parent mkdir).
    trial_db = trial_root / "articles.db"
    _write_corpus_to_db(trial_db, author, corpus.combined_articles)

    extract_all_features(
        trial_db,
        settings,
        author_slug=author.slug,
        project_root=trial_root,
    )
    paths = AnalysisArtifactPaths.from_project(trial_root, trial_db)
    analysis_map = run_full_analysis(paths, settings, author_slug=author.slug)
    return analysis_map.get(author.slug)


@dataclass(frozen=True)
class _RunContext:
    """Immutable configuration bundle passed to trial helpers."""

    settings: ForensicsSettings
    project_root: Path
    run_dir: Path
    author: Author
    articles: list[Article]
    ai_articles: list[Article] = field(default_factory=list)


async def _execute_trial(
    ctx: _RunContext,
    corpus: SyntheticCorpus,
    *,
    trial_dir: Path,
    label: str,
) -> _TrialOutcome:
    """Run a single trial's extract+analyze step and convert it to an outcome."""
    try:
        analysis = await _run_trial_analysis(
            corpus,
            ctx.author,
            settings=ctx.settings,
            project_root=ctx.project_root,
            trial_root=trial_dir,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("calibration: %s failed (%s)", label, exc, exc_info=True)
        analysis = None
    return _outcome_from_analysis(analysis)


async def _run_positive_trials(
    ctx: _RunContext,
    n: int,
    rng: np.random.Generator,
) -> list[CalibrationTrial]:
    trials: list[CalibrationTrial] = []
    for i in range(n):
        splice_date = _pick_splice_date(ctx.articles, rng)
        corpus = build_spliced_corpus(
            ctx.author.slug,
            ctx.articles,
            splice_date,
            ctx.ai_articles,
        )
        outcome = await _execute_trial(
            ctx,
            corpus,
            trial_dir=ctx.run_dir / f"positive_{i:02d}",
            label=f"positive trial {i}",
        )
        date_err = (
            abs((outcome.detection_date - splice_date).days)
            if outcome.detection_date is not None
            else None
        )
        trials.append(
            CalibrationTrial(
                author_slug=ctx.author.slug,
                splice_date=splice_date,
                is_positive=True,
                detected=outcome.detected,
                detection_date=outcome.detection_date,
                composite_score=outcome.composite_score,
                convergence_windows=outcome.convergence_windows,
                date_error_days=date_err,
            )
        )
    return trials


async def _run_negative_trials(ctx: _RunContext, n: int) -> list[CalibrationTrial]:
    trials: list[CalibrationTrial] = []
    for i in range(n):
        corpus = build_negative_control(ctx.author.slug, ctx.articles)
        outcome = await _execute_trial(
            ctx,
            corpus,
            trial_dir=ctx.run_dir / f"negative_{i:02d}",
            label=f"negative trial {i}",
        )
        trials.append(
            CalibrationTrial(
                author_slug=ctx.author.slug,
                splice_date=None,
                is_positive=False,
                detected=outcome.detected,
                detection_date=outcome.detection_date,
                composite_score=outcome.composite_score,
                convergence_windows=outcome.convergence_windows,
                date_error_days=None,
            )
        )
    return trials


async def run_calibration(
    settings: ForensicsSettings,
    *,
    positive_trials: int = 5,
    negative_trials: int = 5,
    author: str | None = None,
    seed: int = 42,
    project_root: Path | None = None,
    db_path: Path | None = None,
    output_path: Path | None = None,
    dry_run: bool = False,
) -> CalibrationReport:
    """Run calibration trials and compute accuracy metrics.

    Args:
        settings: Loaded :class:`ForensicsSettings`.
        positive_trials: Number of spliced corpus trials (should fire).
        negative_trials: Number of unmodified corpus trials (should not fire).
        author: Optional specific author slug; defaults to the most prolific.
        seed: Deterministic seed for splice-date selection.
        project_root: Override the project root. Defaults to
            :func:`forensics.config.get_project_root`.
        db_path: Override the articles database path. Defaults to
            ``<project_root>/data/articles.db``.
        output_path: Override the JSON report location. Defaults to
            ``<project_root>/data/calibration/calibration_<timestamp>.json``.
        dry_run: If ``True``, skip the expensive extract+analyze stages and
            return a report with zero trials — useful for CLI smoke tests.
    """
    from forensics.config import get_project_root

    root = project_root if project_root is not None else get_project_root()
    db = db_path if db_path is not None else root / DEFAULT_DB_RELATIVE

    rng = np.random.default_rng(seed)
    run_timestamp = utc_archive_stamp()
    run_dir = root / "data" / "calibration" / f"run_{run_timestamp}"

    if dry_run:
        logger.info("calibration: dry-run — skipping trial execution")
        report = CalibrationReport(
            trials=[],
            sensitivity=0.0,
            specificity=0.0,
            precision=0.0,
            f1_score=0.0,
            median_date_error_days=None,
        )
        return report

    # run_dir is created by the first write helper that lands an artifact into it.
    target_author, articles = _load_author_articles(db, author)
    if not articles:
        raise ValueError(f"author {target_author.slug!r} has no articles")

    ai_articles = _load_ai_articles(root, target_author)
    ctx = _RunContext(
        settings=settings,
        project_root=root,
        run_dir=run_dir,
        author=target_author,
        articles=articles,
        ai_articles=ai_articles,
    )

    logger.info(
        "calibration: starting — author=%s articles=%d positive=%d negative=%d seed=%d",
        target_author.slug,
        len(articles),
        positive_trials,
        negative_trials,
        seed,
    )

    trials = await _run_positive_trials(ctx, positive_trials, rng)
    trials.extend(await _run_negative_trials(ctx, negative_trials))

    metrics = compute_metrics(trials)
    report_path = output_path or (
        root / "data" / "calibration" / f"calibration_{run_timestamp}.json"
    )
    report = CalibrationReport(
        trials=trials,
        sensitivity=metrics["sensitivity"],
        specificity=metrics["specificity"],
        precision=metrics["precision"],
        f1_score=metrics["f1_score"],
        median_date_error_days=metrics["median_date_error_days"],
        report_path=report_path,
    )
    _write_calibration_report(report, report_path)
    return report


def _write_calibration_report(report: CalibrationReport, output_path: Path) -> None:
    # write_json_artifact (below) mkdirs the parent directory itself.
    payload: dict[str, Any] = {
        "sensitivity": report.sensitivity,
        "specificity": report.specificity,
        "precision": report.precision,
        "f1_score": report.f1_score,
        "median_date_error_days": report.median_date_error_days,
        "n_trials": len(report.trials),
        "trials": [
            {
                "author": t.author_slug,
                "splice_date": t.splice_date.isoformat() if t.splice_date else None,
                "is_positive": t.is_positive,
                "detected": t.detected,
                "detection_date": t.detection_date.isoformat() if t.detection_date else None,
                "composite_score": t.composite_score,
                "convergence_windows": t.convergence_windows,
                "date_error_days": t.date_error_days,
            }
            for t in report.trials
        ],
    }
    write_json_artifact(output_path, payload)
    logger.info("calibration: report written to %s", output_path)
