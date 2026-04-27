"""Integration-suite fixtures (PR94 item 15 — settings cache hygiene)."""

from __future__ import annotations

import pytest

from forensics.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache_integration() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
