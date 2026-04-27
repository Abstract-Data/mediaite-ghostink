"""Chain-of-custody hooks on raw HTML archive (tar.gz) paths."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from forensics.config.settings import AuthorConfig, ChainOfCustodyConfig, ForensicsSettings
from forensics.models.article import Article
from forensics.models.author import Author
from forensics.scraper.fetcher import archive_raw_year_dirs
from forensics.storage.repository import Repository, init_db


def test_archive_raw_year_dirs_logs_when_verify_raw_archives_enabled(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_year = tmp_path / "data" / "raw" / "2020"
    raw_year.mkdir(parents=True)
    (raw_year / "a1.html").write_text("<html>hi</html>", encoding="utf-8")

    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    author_cfg = AuthorConfig(
        name="Fixture",
        slug="fixture-author",
        outlet="mediaite.com",
        role="target",
        archive_url="https://www.mediaite.com/author/fixture-author/",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2021, 1, 1),
    )
    settings = ForensicsSettings(
        authors=[author_cfg],
        chain_of_custody=ChainOfCustodyConfig(verify_raw_archives=True),
    )
    db_author = Author(
        id="author-fixture-author",
        name="Fixture",
        slug="fixture-author",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2021, 1, 1),
        archive_url="https://www.mediaite.com/author/fixture-author/",
    )
    art = Article(
        id="art-1",
        author_id=db_author.id,
        url="https://example.com/1",
        title="t",
        published_date=datetime(2020, 6, 1, tzinfo=UTC),
        clean_text="",
        word_count=0,
        content_hash="h1",
        raw_html_path="raw/2020/a1.html",
    )
    with Repository(db_path) as repo:
        repo.upsert_author(db_author)
        repo.upsert_article(art)

    with caplog.at_level(logging.INFO, logger="forensics.scraper.fetcher"):
        n = archive_raw_year_dirs(tmp_path, db_path, settings=settings)
    assert n == 1
    tgz = tmp_path / "data" / "raw" / "2020.tar.gz"
    assert tgz.is_file()
    assert "chain_of_custody: verified raw archive" in caplog.text
