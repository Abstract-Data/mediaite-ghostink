"""Constructor validation for :class:`ArticleHtmlFetchContext`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forensics.config.settings import ScrapingConfig
from forensics.scraper.fetcher import (
    ArticleHtmlFetchContext,
    FetchConfig,
    FetchSession,
    RateLimiter,
)
from forensics.storage.repository import Repository


def _minimal_fetch_config(tmp_path: Path) -> FetchConfig:
    return FetchConfig(
        root=tmp_path,
        scraping=ScrapingConfig(),
        errors=tmp_path / "e.jsonl",
        coauth=tmp_path / "c.jsonl",
        warns=tmp_path / "w.jsonl",
        total=1,
    )


def _minimal_fetch_session(tmp_path: Path, repo: Repository | MagicMock) -> FetchSession:
    return FetchSession(
        repo=repo,  # type: ignore[arg-type]
        limiter=RateLimiter(0.0, 0.0),
        sem=asyncio.Semaphore(1),
        db_lock=asyncio.Lock(),
        done_lock=asyncio.Lock(),
        done_count=[0],
    )


def test_context_rejects_only_config_without_session(tmp_path: Path) -> None:
    cfg = _minimal_fetch_config(tmp_path)
    with pytest.raises(TypeError, match="both `config` and `session`"):
        ArticleHtmlFetchContext(config=cfg)


def test_context_rejects_only_session_without_config(tmp_path: Path) -> None:
    repo = MagicMock(spec=Repository)
    sess = _minimal_fetch_session(tmp_path, repo)
    with pytest.raises(TypeError, match="both `config` and `session`"):
        ArticleHtmlFetchContext(session=sess)


def test_context_rejects_legacy_kwargs_with_config_and_session(tmp_path: Path) -> None:
    cfg = _minimal_fetch_config(tmp_path)
    repo = MagicMock(spec=Repository)
    sess = _minimal_fetch_session(tmp_path, repo)
    with pytest.raises(TypeError, match="do not pass legacy"):
        ArticleHtmlFetchContext(config=cfg, session=sess, repo=repo)


def test_context_legacy_path_reports_missing_fields(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="missing required:.*repo"):
        ArticleHtmlFetchContext(
            root=tmp_path,
            scraping=ScrapingConfig(),
            limiter=RateLimiter(0.0, 0.0),
            errors=tmp_path / "e.jsonl",
            coauth=tmp_path / "c.jsonl",
            warns=tmp_path / "w.jsonl",
            sem=asyncio.Semaphore(1),
            db_lock=asyncio.Lock(),
            done_lock=asyncio.Lock(),
            done_count=[0],
            total=1,
        )
