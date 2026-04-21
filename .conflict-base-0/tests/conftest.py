"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from forensics.config import get_settings
from forensics.models import Article, Author
from forensics.scraper.crawler import stable_article_id

MINIMAL_CONFIG_TOML = """
[[authors]]
name = "Fixture Author"
slug = "fixture-author"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/fixture-author/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[scraping]

[analysis]

[report]
"""


@pytest.fixture
def forensics_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "config.toml"
    path.write_text(MINIMAL_CONFIG_TOML.strip() + "\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


@pytest.fixture
def settings(forensics_config_path: Path):
    return get_settings()


@pytest.fixture
def tmp_db(tmp_path):
    from forensics.storage.repository import init_db

    db_path = tmp_path / "articles.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def sample_author() -> Author:
    return Author(
        id="author-test-1",
        name="Test Author",
        slug="test-author",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://www.mediaite.com/author/test-author/",
    )


@pytest.fixture
def sample_article(sample_author: Author) -> Article:
    url = "https://www.mediaite.com/2024/01/02/example-post/"
    return Article(
        id=stable_article_id(url),
        author_id=sample_author.id,
        url=url,
        title="Example Post",
        published_date=datetime(2024, 1, 2, tzinfo=UTC),
        clean_text="",
        word_count=0,
        content_hash="",
    )
