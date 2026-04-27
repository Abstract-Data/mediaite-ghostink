"""Config file fingerprint for ``analysis_runs`` audit rows."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from forensics.config.settings import ForensicsSettings, get_project_root
from forensics.utils.provenance import compute_model_config_hash


def config_fingerprint() -> str | None:
    """Short hash of the active TOML config file for ``analysis_runs``.

    Returns ``None`` when no config file is found — callers must skip the
    ``analysis_runs`` row rather than persist a sentinel hash that would
    collide across unrelated config-less runs.
    """
    raw = os.environ.get("FORENSICS_CONFIG_FILE", "").strip()
    candidates: list[Path] = [Path(raw).expanduser()] if raw else []
    candidates.append(get_project_root() / "config.toml")
    for path in candidates:
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return digest[:48]
    return None


def scraper_signal_digest(settings: ForensicsSettings) -> str:
    """I-01 — short hash of signal-bearing scraper knobs (subset of full config)."""
    return compute_model_config_hash(settings.scraping, length=16, round_trip=True)
