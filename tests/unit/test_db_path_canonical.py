"""Canonical SQLite path matches ``ForensicsSettings.db_path``."""

from __future__ import annotations

from forensics.config import DEFAULT_DB_RELATIVE, get_project_root, get_settings


def test_settings_db_path_matches_root_join_default_relative() -> None:
    """Default corpus path is project root + ``DEFAULT_DB_RELATIVE`` (single source)."""
    get_settings.cache_clear()
    root = get_project_root()
    settings = get_settings()
    assert settings.db_path == root / DEFAULT_DB_RELATIVE
