"""Author qualification filter for blind survey mode (Phase 12 §1b)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

from forensics.config.settings import SurveyConfig
from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.repository import Repository
from forensics.survey.shared_byline import matching_rule as _shared_byline_rule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QualificationCriteria:
    """Minimum thresholds for including an author in the survey.

    Mirrors :class:`forensics.config.settings.SurveyConfig` so callers may
    override on the CLI without mutating the global settings object.
    """

    min_articles: int = 50
    min_span_days: int = 730
    min_words_per_article: int = 200
    min_articles_per_year: float = 12.0
    require_recent_activity: bool = True
    recent_activity_days: int = 180
    # Phase 15 D — exclude newsroom-shared accounts (e.g. ``mediaite-staff``).
    exclude_shared_bylines: bool = True

    @classmethod
    def from_settings(cls, survey: SurveyConfig) -> QualificationCriteria:
        return cls(
            min_articles=survey.min_articles,
            min_span_days=survey.min_span_days,
            min_words_per_article=survey.min_words_per_article,
            min_articles_per_year=survey.min_articles_per_year,
            require_recent_activity=survey.require_recent_activity,
            recent_activity_days=survey.recent_activity_days,
            exclude_shared_bylines=survey.exclude_shared_bylines,
        )


@dataclass(frozen=True)
class QualifiedAuthor:
    """An author evaluated against the survey qualification criteria."""

    author: Author
    total_articles: int
    date_range_days: int
    earliest_article: date
    latest_article: date
    avg_word_count: float
    articles_per_year: float
    disqualification_reason: str | None = None


def _build_empty_dq(author: Author, reason: str) -> QualifiedAuthor:
    return QualifiedAuthor(
        author=author,
        total_articles=0,
        date_range_days=0,
        earliest_article=date.min,
        latest_article=date.min,
        avg_word_count=0.0,
        articles_per_year=0.0,
        disqualification_reason=reason,
    )


def _summarize_author(author: Author, articles: list[Article]) -> QualifiedAuthor | None:
    """Compute summary stats for an author; returns ``None`` if stats are unusable."""
    dates = sorted(a.published_date.date() for a in articles if a.published_date is not None)
    # word_count is always an int on the Article model; filter on positive values only.
    word_counts = [a.word_count for a in articles if a.word_count > 0]
    if not dates or not word_counts:
        return None

    span_days = (dates[-1] - dates[0]).days
    avg_wc = sum(word_counts) / len(word_counts)
    years = max(span_days / 365.25, 0.01)
    articles_per_year = len(articles) / years

    return QualifiedAuthor(
        author=author,
        total_articles=len(articles),
        date_range_days=span_days,
        earliest_article=dates[0],
        latest_article=dates[-1],
        avg_word_count=avg_wc,
        articles_per_year=articles_per_year,
    )


def _shared_byline_disqualify(
    author: Author,
    criteria: QualificationCriteria,
) -> str | None:
    """Return a disqualification reason if the author is a shared byline.

    Honours the persisted ``Author.is_shared_byline`` flag (Phase 0 / Phase D)
    and re-runs the heuristic so older databases that pre-date the migration
    backfill are still handled. If neither fires, returns ``None``.
    """
    if not criteria.exclude_shared_bylines:
        return None
    rule = _shared_byline_rule(author.slug, author.name, author.outlet)
    if rule is None and not author.is_shared_byline:
        return None
    return f"shared_byline ({rule or 'flagged'})"


def _check_criteria(
    qa: QualifiedAuthor,
    criteria: QualificationCriteria,
    *,
    today: date | None = None,
) -> str | None:
    """Return a disqualification reason string, or ``None`` if the author qualifies."""
    if qa.total_articles < criteria.min_articles:
        return f"too_few_articles ({qa.total_articles} < {criteria.min_articles})"
    if qa.date_range_days < criteria.min_span_days:
        return f"date_range_too_short ({qa.date_range_days}d < {criteria.min_span_days}d)"
    if qa.avg_word_count < criteria.min_words_per_article:
        return (
            f"avg_word_count_too_low ({qa.avg_word_count:.0f} < {criteria.min_words_per_article})"
        )
    if qa.articles_per_year < criteria.min_articles_per_year:
        return (
            f"publishing_frequency_too_low "
            f"({qa.articles_per_year:.1f}/yr < {criteria.min_articles_per_year}/yr)"
        )
    if criteria.require_recent_activity:
        reference = today if today is not None else date.today()
        cutoff = reference - timedelta(days=criteria.recent_activity_days)
        if qa.latest_article < cutoff:
            return f"no_recent_activity (last: {qa.latest_article}, cutoff: {cutoff})"
    return None


def qualify_authors(
    db_path: Path,
    criteria: QualificationCriteria | None = None,
    *,
    today: date | None = None,
) -> tuple[list[QualifiedAuthor], list[QualifiedAuthor]]:
    """Evaluate all authors in the corpus against the qualification criteria.

    Args:
        db_path: Path to ``articles.db``.
        criteria: Optional custom criteria; defaults to ``QualificationCriteria()``.
        today: Anchor date for "recent activity" (useful for tests).

    Returns:
        ``(qualified, disqualified)`` — both lists contain stats for transparency.
    """
    if criteria is None:
        criteria = QualificationCriteria()

    qualified: list[QualifiedAuthor] = []
    disqualified: list[QualifiedAuthor] = []

    with Repository(db_path) as repo:
        authors = repo.all_authors()
        for author in authors:
            # Shared-byline gate runs before counting articles so we don't
            # waste IO on accounts we'd reject anyway.
            shared_reason = _shared_byline_disqualify(author, criteria)
            if shared_reason is not None:
                disqualified.append(_build_empty_dq(author, shared_reason))
                continue

            articles = repo.get_articles_by_author(author.id)
            if not articles:
                disqualified.append(_build_empty_dq(author, "no_articles"))
                continue

            qa = _summarize_author(author, articles)
            if qa is None:
                disqualified.append(_build_empty_dq(author, "missing_dates_or_wordcounts"))
                continue

            reason = _check_criteria(qa, criteria, today=today)
            if reason is not None:
                disqualified.append(replace(qa, disqualification_reason=reason))
            else:
                qualified.append(qa)

    logger.info(
        "qualification: %d qualified, %d disqualified out of %d total authors",
        len(qualified),
        len(disqualified),
        len(qualified) + len(disqualified),
    )
    return qualified, disqualified
