"""Phase 15 D — shared-byline heuristic and qualification gate."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from forensics.models import Article, Author
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository
from forensics.survey.qualification import (
    QualificationCriteria,
    qualify_authors,
)
from forensics.survey.shared_byline import is_shared_byline, matching_rule

OUTLET = "mediaite.com"


@pytest.mark.parametrize(
    ("slug", "name"),
    [
        ("mediaite", "Mediaite"),
        ("mediaite-staff", "Mediaite Staff"),
        ("the-daily-staff", "The Daily Staff"),
        ("jane-doe-and-john-smith", "Jane Doe and John Smith"),
        ("politics-desk", "Politics Desk"),
        ("editorial-team", "Editorial Team"),
        ("ap-wire", "AP Wire"),
        ("contributors", "Contributors"),
    ],
)
def test_is_shared_byline_positive(slug: str, name: str) -> None:
    assert is_shared_byline(slug, name, OUTLET) is True
    assert matching_rule(slug, name, OUTLET) is not None


@pytest.mark.parametrize(
    ("slug", "name"),
    [
        # Famous "and" / "&" lookalike false-positive guards.
        ("brandon-morse", "Brandon Morse"),
        ("sandra-doe", "Sandra Doe"),
        ("alexander-smith", "Alexander Smith"),
        # Real Mediaite reporters per spec.
        ("sarah-rumpf", "Sarah Rumpf"),
        ("isaac-schorr", "Isaac Schorr"),
        # Single-name authors and ones that include "team-" prefix in unrelated
        # contexts but no shared token in slug components.
        ("tommy-christopher", "Tommy Christopher"),
        ("jane-doe", "Jane Doe"),
    ],
)
def test_is_shared_byline_negative(slug: str, name: str) -> None:
    assert is_shared_byline(slug, name, OUTLET) is False
    assert matching_rule(slug, name, OUTLET) is None


def test_is_shared_byline_and_requires_whitespace_both_sides() -> None:
    """``Brandon`` contains substring ``and`` — must NOT match (P15-D guard)."""
    assert is_shared_byline("brandon", "Brandon", OUTLET) is False


def test_matching_rule_labels() -> None:
    """Spot-check that the rule label disambiguates which heuristic fired."""
    assert matching_rule("mediaite", "Mediaite", OUTLET) == "outlet_slug"
    assert matching_rule("mediaite-staff", "Mediaite Staff", OUTLET) == "outlet_prefix"
    assert matching_rule("the-daily-staff", "The Daily Staff", OUTLET) == "token:staff"
    assert (
        matching_rule("jane-doe-and-john-smith", "Jane Doe and John Smith", OUTLET)
        == "multi_author_conjunction"
    )


def test_author_model_default_is_shared_byline_false() -> None:
    author = Author(
        id="author-x",
        name="John Smith",
        slug="john-smith",
        outlet=OUTLET,
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://www.mediaite.com/author/john-smith/",
    )
    assert author.is_shared_byline is False
    upgraded = author.with_updates(is_shared_byline=True)
    assert upgraded.is_shared_byline is True
    # original frozen instance untouched
    assert author.is_shared_byline is False


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


def _make_article(author: Author, *, published: datetime, words: int = 400) -> Article:
    url = f"https://www.mediaite.com/{published.year}/{published.month:02d}/{uuid4().hex[:8]}/"
    return Article(
        id=stable_article_id(url),
        author_id=author.id,
        url=url,
        title=f"Post {published.date().isoformat()}",
        published_date=published,
        clean_text="body " * max(words, 1),
        word_count=words,
        content_hash=f"hash-{uuid4().hex[:8]}",
    )


def _seed(db: Path, authors: list[Author], articles: list[Article]) -> None:
    with Repository(db) as repo:
        for a in authors:
            repo.upsert_author(a)
        for art in articles:
            repo.upsert_article(art)


def _high_volume_articles(author: Author) -> list[Article]:
    """Enough articles to satisfy default thresholds (60 articles, 3-year span)."""
    start = datetime(2021, 1, 1, tzinfo=UTC)
    return [_make_article(author, published=start + timedelta(days=i * 20)) for i in range(60)]


def test_qualification_excludes_shared_byline_by_default(tmp_db: Path) -> None:
    shared = _make_author("mediaite-staff", name="Mediaite Staff", shared=True)
    real = _make_author("isaac-schorr", name="Isaac Schorr")
    articles = _high_volume_articles(shared) + _high_volume_articles(real)
    _seed(tmp_db, [shared, real], articles)

    qualified, disqualified = qualify_authors(tmp_db, today=date(2024, 6, 1))

    qualified_slugs = {q.author.slug for q in qualified}
    disqualified_slugs = {d.author.slug for d in disqualified}
    assert "isaac-schorr" in qualified_slugs
    assert "mediaite-staff" in disqualified_slugs

    shared_dq = next(d for d in disqualified if d.author.slug == "mediaite-staff")
    reason = shared_dq.disqualification_reason or ""
    assert reason.startswith("shared_byline (")
    assert "outlet_prefix" in reason


def test_qualification_excludes_unflagged_shared_via_heuristic(tmp_db: Path) -> None:
    """Even when ``is_shared_byline`` was never persisted, the slug heuristic fires."""
    shared = _make_author("mediaite", name="Mediaite", shared=False)
    articles = _high_volume_articles(shared)
    _seed(tmp_db, [shared], articles)

    _, disqualified = qualify_authors(tmp_db, today=date(2024, 6, 1))
    slugs = {d.author.slug: d.disqualification_reason or "" for d in disqualified}
    assert slugs.get("mediaite", "").startswith("shared_byline (")


def test_include_shared_bylines_flag_reincludes(tmp_db: Path) -> None:
    shared = _make_author("mediaite-staff", name="Mediaite Staff", shared=True)
    articles = _high_volume_articles(shared)
    _seed(tmp_db, [shared], articles)

    criteria = QualificationCriteria(exclude_shared_bylines=False)
    qualified, disqualified = qualify_authors(tmp_db, criteria, today=date(2024, 6, 1))

    qualified_slugs = {q.author.slug for q in qualified}
    disqualified_slugs = {d.author.slug for d in disqualified}
    assert "mediaite-staff" in qualified_slugs
    assert "mediaite-staff" not in disqualified_slugs


def test_qualification_criteria_from_settings_propagates_flag() -> None:
    from forensics.config.settings import SurveyConfig

    cfg_default = SurveyConfig()
    crit_default = QualificationCriteria.from_settings(cfg_default)
    assert crit_default.exclude_shared_bylines is True

    cfg_off = SurveyConfig(exclude_shared_bylines=False)
    crit_off = QualificationCriteria.from_settings(cfg_off)
    assert crit_off.exclude_shared_bylines is False
