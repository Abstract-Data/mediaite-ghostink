"""Shared CLI helpers — config fingerprint, placeholder guard, logging."""

from __future__ import annotations

import logging

import typer

from forensics.config.settings import ForensicsSettings

logger = logging.getLogger(__name__)

_PLACEHOLDER_SLUGS = frozenset({"placeholder-target", "placeholder-control"})


def guard_placeholder_authors(settings: ForensicsSettings) -> None:
    """Reject template slugs before any live scrape stage (P3-SEC-3)."""
    if any(a.slug in _PLACEHOLDER_SLUGS for a in settings.authors):
        raise typer.BadParameter(
            "config.toml still uses template authors (slug placeholder-target / "
            "placeholder-control). Replace them with real author rows before scraping."
        )
