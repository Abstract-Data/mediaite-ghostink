"""Tests for :func:`forensics.storage.repository.ensure_repo`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from forensics.storage.repository import Repository, ensure_repo, init_db


def test_ensure_repo_yields_injected_repository(tmp_path: Path) -> None:
    db_path = tmp_path / "unused.db"
    injected = MagicMock(spec=Repository)
    with ensure_repo(db_path, injected) as repo:
        assert repo is injected


def test_ensure_repo_opens_repository_when_none(tmp_path: Path) -> None:
    db_path = tmp_path / "articles.db"
    init_db(db_path)
    with ensure_repo(db_path, None) as repo:
        assert isinstance(repo, Repository)
        assert repo.all_authors() == []
