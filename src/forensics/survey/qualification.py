"""Author qualification filter for blind survey mode (Phase 12 §1b)."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from forensics.config.settings import SurveyConfig
from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.repository import Repository
from forensics.survey.shared_byline import matching_rule as _shared_byline_rule
from forensics.utils.url import section_from_url

logger = logging.getLogger(__name__)


# Public CSV contract; tests assert this header tuple exactly.
EXCLUDED_ARTICLES_CSV_HEADER: tuple[str, ...] = (
    "id",
    "url",
    "author",
    "section",
    "reason",
    "likely_author_own_work",
)
EXCLUDED_ARTICLES_CSV_RELPATH = Path("data") / "survey" / "excluded_articles.csv"


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
    # Phase 15 J2 — drop advertorial / syndicated sections from volume,
    # recency, and frequency stats before checking the qualification gates.
    excluded_sections: frozenset[str] = field(
        default_factory=lambda: frozenset({"sponsored", "partner-content", "crosspost"})
    )

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
            excluded_sections=frozenset(survey.excluded_sections),
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


@dataclass(frozen=True, slots=True)
class _ExcludedRow:
    """One audit-CSV row for an article dropped by section exclusion."""

    article_id: str
    url: str
    author_slug: str
    section: str
    reason: str
    likely_author_own_work: bool


def _split_excluded_articles(
    author: Author,
    articles: list[Article],
    excluded: frozenset[str],
) -> tuple[list[Article], list[_ExcludedRow]]:
    """Partition ``articles`` into (kept, excluded-rows-with-audit-metadata).

    ``crosspost`` rows by an author who is *not* a shared byline are flagged
    ``likely_author_own_work=True`` per the J2 spec — informational only; they
    are still excluded by default.
    """
    if not excluded:
        return articles, []
    kept: list[Article] = []
    rows: list[_ExcludedRow] = []
    for art in articles:
        section = section_from_url(str(art.url))
        if section not in excluded:
            kept.append(art)
            continue
        likely_own = section == "crosspost" and not author.is_shared_byline
        rows.append(
            _ExcludedRow(
                article_id=art.id,
                url=str(art.url),
                author_slug=author.slug,
                section=section,
                reason=f"section_excluded ({section})",
                likely_author_own_work=likely_own,
            )
        )
    return kept, rows


def _write_excluded_articles_csv(
    rows: list[_ExcludedRow],
    csv_path: Path,
) -> None:
    """Write the audit CSV with the pinned header. Always rewrites in-place."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(EXCLUDED_ARTICLES_CSV_HEADER)
        for r in rows:
            writer.writerow(
                [
                    r.article_id,
                    r.url,
                    r.author_slug,
                    r.section,
                    r.reason,
                    "true" if r.likely_author_own_work else "false",
                ]
            )


def _resolve_audit_csv_path(
    db_path: Path,
    explicit: Path | None,
) -> Path | None:
    """Pick the audit-CSV destination, or return ``None`` to skip the write.

    Callers may pass ``explicit`` to override; otherwise we infer
    ``<project_root>/data/survey/excluded_articles.csv`` from the ``db_path``
    layout (``<project_root>/data/articles.db``). Returns ``None`` if the
    layout isn't recognisable so unit tests with bare temp DBs don't trigger
    a write into someone's home directory.
    """
    if explicit is not None:
        return explicit
    if db_path.name == "articles.db" and db_path.parent.name == "data":
        return db_path.parent.parent / EXCLUDED_ARTICLES_CSV_RELPATH
    return None


def qualify_authors(
    db_path: Path,
    criteria: QualificationCriteria | None = None,
    *,
    today: date | None = None,
    audit_csv_path: Path | None = None,
) -> tuple[list[QualifiedAuthor], list[QualifiedAuthor]]:
    """Evaluate all authors in the corpus against the qualification criteria.

    Args:
        db_path: Path to ``articles.db``.
        criteria: Optional custom criteria; defaults to ``QualificationCriteria()``.
        today: Anchor date for "recent activity" (useful for tests).
        audit_csv_path: If set, dump the section-exclusion audit CSV to this
            path. Defaults to ``<project>/data/survey/excluded_articles.csv``
            inferred from ``db_path`` (``data/articles.db``); pass ``None``
            inside tests to skip the write entirely by also setting
            ``criteria.excluded_sections`` to ``frozenset()``.

    Returns:
        ``(qualified, disqualified)`` — both lists contain stats for transparency.
    """
    if criteria is None:
        criteria = QualificationCriteria()

    qualified: list[QualifiedAuthor] = []
    disqualified: list[QualifiedAuthor] = []
    excluded_rows: list[_ExcludedRow] = []

    with Repository(db_path) as repo:
        authors = repo.all_authors()
        for author in authors:
            # Shared-byline gate runs before counting articles so we don't
            # waste IO on accounts we'd reject anyway.
            shared_reason = _shared_byline_disqualify(author, criteria)
            if shared_reason is not None:
                disqualified.append(_build_empty_dq(author, shared_reason))
                continue

            raw_articles = repo.get_articles_by_author(author.id)
            articles, dropped = _split_excluded_articles(
                author, raw_articles, criteria.excluded_sections
            )
            excluded_rows.extend(dropped)

            if not articles:
                # Distinguish "never wrote anything" from "wrote only excluded
                # sections" so the disqualification log is actionable.
                reason = "no_articles" if not raw_articles else "all_articles_excluded_by_section"
                disqualified.append(_build_empty_dq(author, reason))
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

    csv_target = _resolve_audit_csv_path(db_path, audit_csv_path)
    if csv_target is not None:
        _write_excluded_articles_csv(excluded_rows, csv_target)
        logger.info(
            "qualification: %d article(s) excluded by section -> %s",
            len(excluded_rows),
            csv_target,
        )

    logger.info(
        "qualification: %d qualified, %d disqualified out of %d total authors",
        len(qualified),
        len(disqualified),
        len(qualified) + len(disqualified),
    )
    return qualified, disqualified
