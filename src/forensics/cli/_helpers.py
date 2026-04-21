"""Shared CLI helpers — config fingerprint, placeholder guard."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import typer

from forensics.config import get_project_root
from forensics.config.settings import ForensicsSettings

_PLACEHOLDER_SLUGS = frozenset({"placeholder-target", "placeholder-control"})


def config_fingerprint() -> str:
    """Short hash of the active TOML config file for ``analysis_runs``."""
    raw = os.environ.get("FORENSICS_CONFIG_FILE", "").strip()
    candidates = [Path(raw).expanduser()] if raw else []
    candidates.append(get_project_root() / "config.toml")
    for path in candidates:
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return digest[:48]
    return "no_config_file"


def guard_placeholder_authors(settings: ForensicsSettings) -> None:
    """Reject template slugs before any live scrape stage (P3-SEC-3).

    Raises typer.BadParameter if placeholder authors detected.
    """
    if any(a.slug in _PLACEHOLDER_SLUGS for a in settings.authors):
        raise typer.BadParameter(
            "config.toml still uses template authors (slug placeholder-target / "
            "placeholder-control). Replace them with real author rows before scraping."
        )
