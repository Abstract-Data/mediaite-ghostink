"""Phase 15 J2 — exclude advertorial / syndicated sections from survey + features."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from forensics.models import Article, Author
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository
from forensics.survey.qualification import (
    EXCLUDED_ARTICLES_CSV_HEADER,
    EXCLUDED_ARTICLES_CSV_RELPATH,
    QualificationCriteria,
    qualify_authors,
)

OUTLET = "mediaite.com"


def _make_author(slug: str, *, name: str | None = None, shared: bool = False) -> Author:
    return Author(
        id=f"author-{slug}",
        name=name or slug.title().replace("-", " "),
        slug=slug,
        outlet=OUTLET,
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url=f"https://www.mediaite.com/author/{slug}/",
        is_shared_byline=shared,
    )


def _make_article(
    author: Author,
    *,
    published: datetime,
    section: str = "news",
    words: int = 400,
) -> Article:
    """Build an article whose URL puts it in ``section`` (first path segment)."""
    suffix = uuid4().hex[:8]
    url = f"https://www.mediaite.com/{section}/{published.year}/{published.month:02d}/{suffix}/"
    return Article(
        id=stable_article_id(url),
        author_id=author.id,
        url=url,
        title=f"Post {published.date().isoformat()} {suffix}",
        published_date=published,
        clean_text="body " * max(words, 1),
        word_count=words,
        content_hash=f"hash-{suffix}",
    )


def _seed(db: Path, authors: list[Author], articles: list[Article]) -> None:
    with Repository(db) as repo:
        for a in authors:
            repo.upsert_author(a)
        for art in articles:
            repo.upsert_article(art)


def _news_articles(author: Author, *, count: int = 60, section: str = "news") -> list[Article]:
    """Enough non-excluded articles to clear default qualification thresholds."""
    start = datetime(2021, 1, 1, tzinfo=UTC)
    return [
        _make_article(author, published=start + timedelta(days=i * 20), section=section)
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# happy path: a sponsored article does not count toward qualification volume
# ---------------------------------------------------------------------------


def test_sponsored_article_excluded_from_volume_count(tmp_db: Path, tmp_path: Path) -> None:
    author = _make_author("real-reporter")
    # 60 valid news articles (clears min_articles=50) + 5 sponsored articles
    # that should NOT contribute to the volume count.
    articles = _news_articles(author, count=60) + [
        _make_article(
            author,
            published=datetime(2022, 6, 1, tzinfo=UTC) + timedelta(days=i),
            section="sponsored",
        )
        for i in range(5)
    ]
    _seed(tmp_db, [author], articles)

    qualified, _ = qualify_authors(
        tmp_db,
        today=date(2024, 6, 1),
        audit_csv_path=tmp_path / "excluded_articles.csv",
    )

    assert len(qualified) == 1
    qa = qualified[0]
    # 60 kept, 5 sponsored dropped — total_articles must reflect the post-filter count.
    assert qa.total_articles == 60


# ---------------------------------------------------------------------------
# edge case: an entirely-sponsored author drops below min_articles
# ---------------------------------------------------------------------------


def test_author_with_only_sponsored_articles_disqualified(tmp_db: Path, tmp_path: Path) -> None:
    author = _make_author("partner-only")
    # 60 sponsored articles — would qualify on volume alone, but every single
    # one is excluded so the author should be disqualified.
    articles = _news_articles(author, count=60, section="sponsored")
    _seed(tmp_db, [author], articles)

    qualified, disqualified = qualify_authors(
        tmp_db,
        today=date(2024, 6, 1),
        audit_csv_path=tmp_path / "excluded_articles.csv",
    )

    assert qualified == []
    assert len(disqualified) == 1
    dq = disqualified[0]
    assert dq.author.slug == "partner-only"
    assert dq.disqualification_reason == "all_articles_excluded_by_section"


# ---------------------------------------------------------------------------
# regression-pin: CSV header + column order are pinned for spreadsheet consumers
# ---------------------------------------------------------------------------


def test_excluded_articles_csv_header_and_columns_pinned(tmp_db: Path, tmp_path: Path) -> None:
    author = _make_author("real-reporter")
    sponsored = _make_article(
        author, published=datetime(2022, 6, 1, tzinfo=UTC), section="sponsored"
    )
    articles = _news_articles(author, count=50) + [sponsored]
    _seed(tmp_db, [author], articles)

    csv_path = tmp_path / "excluded_articles.csv"
    qualify_authors(tmp_db, today=date(2024, 6, 1), audit_csv_path=csv_path)

    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        rows = list(reader)

    # Pinned header — spreadsheet consumers depend on this exact tuple.
    assert tuple(rows[0]) == EXCLUDED_ARTICLES_CSV_HEADER
    assert EXCLUDED_ARTICLES_CSV_HEADER == (
        "id",
        "url",
        "author",
        "section",
        "reason",
        "likely_author_own_work",
    )

    assert len(rows) == 2  # header + 1 sponsored article
    data_row = dict(zip(EXCLUDED_ARTICLES_CSV_HEADER, rows[1], strict=True))
    assert data_row["id"] == sponsored.id
    assert data_row["url"] == str(sponsored.url)
    assert data_row["author"] == "real-reporter"
    assert data_row["section"] == "sponsored"
    assert data_row["reason"] == "section_excluded (sponsored)"
    # Sponsored is not crosspost, so the own-work flag stays false.
    assert data_row["likely_author_own_work"] == "false"


# ---------------------------------------------------------------------------
# crosspost flag: real (non-shared) author + crosspost == likely_author_own_work
# ---------------------------------------------------------------------------


def test_crosspost_by_real_author_flagged_likely_own_work(tmp_db: Path, tmp_path: Path) -> None:
    author = _make_author("isaac-schorr", name="Isaac Schorr", shared=False)
    crosspost = _make_article(
        author, published=datetime(2022, 6, 1, tzinfo=UTC), section="crosspost"
    )
    articles = _news_articles(author, count=50) + [crosspost]
    _seed(tmp_db, [author], articles)

    csv_path = tmp_path / "excluded_articles.csv"
    qualify_authors(tmp_db, today=date(2024, 6, 1), audit_csv_path=csv_path)

    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    crosspost_rows = [r for r in rows if r["section"] == "crosspost"]
    assert len(crosspost_rows) == 1
    assert crosspost_rows[0]["likely_author_own_work"] == "true"


# ---------------------------------------------------------------------------
# escape hatch: ``--include-advertorial`` re-includes excluded sections
# ---------------------------------------------------------------------------


def test_include_advertorial_reincludes_sponsored(tmp_db: Path, tmp_path: Path) -> None:
    author = _make_author("partner-only")
    # 60 sponsored articles — disqualified under default criteria, qualified
    # when ``excluded_sections`` is overridden to the empty set.
    articles = _news_articles(author, count=60, section="sponsored")
    _seed(tmp_db, [author], articles)

    criteria = QualificationCriteria(excluded_sections=frozenset())
    qualified, disqualified = qualify_authors(
        tmp_db,
        criteria,
        today=date(2024, 6, 1),
        audit_csv_path=tmp_path / "excluded_articles.csv",
    )

    qualified_slugs = {q.author.slug for q in qualified}
    disqualified_slugs = {d.author.slug for d in disqualified}
    assert "partner-only" in qualified_slugs
    assert "partner-only" not in disqualified_slugs


# ---------------------------------------------------------------------------
# settings wiring: SurveyConfig + FeaturesConfig defaults flow through
# ---------------------------------------------------------------------------


def test_qualification_criteria_from_settings_inherits_excluded_sections() -> None:
    from forensics.config.settings import FeaturesConfig, SurveyConfig

    survey = SurveyConfig()
    crit = QualificationCriteria.from_settings(survey)
    assert "sponsored" in crit.excluded_sections
    assert "partner-content" in crit.excluded_sections
    assert "crosspost" in crit.excluded_sections

    # FeaturesConfig mirrors the same default set so a single CLI flag flips both.
    features = FeaturesConfig()
    assert features.excluded_sections == survey.excluded_sections


# ---------------------------------------------------------------------------
# audit CSV path: layout-derived default
# ---------------------------------------------------------------------------


def test_audit_csv_path_constant_uses_data_survey_subdir() -> None:
    assert EXCLUDED_ARTICLES_CSV_RELPATH == Path("data") / "survey" / "excluded_articles.csv"


# ---------------------------------------------------------------------------
# features pipeline: helper drops excluded sections + emits info log
# ---------------------------------------------------------------------------


def test_features_filter_drops_excluded_sections(caplog: pytest.LogCaptureFixture) -> None:
    from forensics.features.pipeline import _filter_excluded_sections

    author = _make_author("real-reporter")
    keep = _make_article(author, published=datetime(2022, 1, 1, tzinfo=UTC), section="news")
    drop = _make_article(author, published=datetime(2022, 1, 2, tzinfo=UTC), section="sponsored")
    excluded = frozenset({"sponsored", "partner-content", "crosspost"})

    with caplog.at_level("INFO", logger="forensics.features.pipeline"):
        kept = _filter_excluded_sections([keep, drop], excluded)

    assert kept == [keep]
    assert any("excluded sections" in rec.getMessage() for rec in caplog.records), (
        "expected an INFO log line summarising the section-exclusion drop"
    )


def test_features_filter_no_op_when_excluded_set_empty() -> None:
    from forensics.features.pipeline import _filter_excluded_sections

    author = _make_author("real-reporter")
    arts = [
        _make_article(author, published=datetime(2022, 1, 1, tzinfo=UTC), section="sponsored"),
        _make_article(author, published=datetime(2022, 1, 2, tzinfo=UTC), section="news"),
    ]
    assert _filter_excluded_sections(arts, frozenset()) == arts
