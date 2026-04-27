"""Seeded two-regime vs single-regime corpora for integration E2E (PR94 item 14)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from forensics.models import Article, Author
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository, init_db

# Deliberate lexical / AI-marker regime shift for changepoint + convergence signal.
_SHIFT_UTC = datetime(2022, 6, 1, 12, 0, 0, tzinfo=UTC)

_PRE_WIRE_BODY = (
    "Cable snip. Brief item. City desk notes another vote. "
    "Wire lead short. Editors trim copy. "
    "Council met. Vote tallied. Opposition spoke. "
    "Forecast dry. Roads open. Patrols watch ramps. "
    "Union talks stall. Plant idle. Shift ends. "
    "Appeals court rules. Brief filed. Hearing set. "
    "Corn slips. Futures dip. Traders watch bins. "
    "Mayor speaks. Bond plan stalls. Sewer funds tight. "
    "Snow line rises. Travelers warned. Chains advised. "
    "Crop yields mixed. Elevators busy. Barges wait."
)

_POST_AI_BODY = (
    "Furthermore it is important to note that this report will unpack how the "
    "tapestry of evidence contributes to a broader understanding and we should "
    "delve into the nuances because stakeholders deserve clarity on next steps "
    "while the landscape shifts and the narrative evolves in ways that merit "
    "careful attention from every responsible observer following the thread. "
    "Moreover it is worth emphasizing that the framework outlined here invites "
    "readers to engage thoughtfully with the implications as the dataset deepens "
    "and the contours of the story become sharper across the full timeline. "
    "Additionally we highlight that transparency remains paramount as teams "
    "synthesize findings and communicate outcomes with precision and care. "
    "Finally we underscore that continued monitoring will surface any residual "
    "patterns that deserve follow-up analysis in subsequent reporting cycles."
)


def seed_two_regime_corpus(
    db_path: Path,
    *,
    shift: datetime = _SHIFT_UTC,
    n_articles: int = 36,
    step_days: int = 45,
) -> datetime:
    """Insert fixture-target (two regimes) + fixture-control (single regime).

    Returns the canonical shift instant used for assertions (±30 day window).
    """
    target = Author(
        id="author-fixture-target",
        name="Fixture Target",
        slug="fixture-target",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2024, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-target/",
    )
    control = Author(
        id="author-fixture-control",
        name="Fixture Control",
        slug="fixture-control",
        outlet="mediaite.com",
        role="control",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2024, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-control/",
    )
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.ensure_schema()
        repo.upsert_author(target)
        repo.upsert_author(control)
        start = datetime(2020, 1, 5, 12, 0, 0, tzinfo=UTC)
        for i in range(n_articles):
            pub = start + timedelta(days=step_days * i)
            for slug, author in (("fixture-target", target), ("fixture-control", control)):
                url = f"https://www.mediaite.com/politics/{slug}-article-{i:03d}/"
                if slug == "fixture-control":
                    body = f"{_PRE_WIRE_BODY} control={slug} idx={i}."
                elif pub < shift:
                    body = f"{_PRE_WIRE_BODY} target=pre idx={i}."
                else:
                    body = f"{_POST_AI_BODY} target=post idx={i}."
                wc = len(body.split())
                aid = stable_article_id(url)
                h = hashlib.sha256(body.encode()).hexdigest()
                art = Article(
                    id=aid,
                    author_id=author.id,
                    url=url,
                    title=f"{slug} headline {i}",
                    published_date=pub,
                    clean_text=body,
                    word_count=wc,
                    content_hash=h,
                )
                repo.upsert_article(art)
    return shift
