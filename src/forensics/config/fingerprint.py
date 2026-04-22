"""Config file fingerprint for ``analysis_runs`` audit rows."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from forensics.config.settings import get_project_root


def config_fingerprint() -> str:
    """Short hash of the active TOML config file for ``analysis_runs``."""
    raw = os.environ.get("FORENSICS_CONFIG_FILE", "").strip()
    candidates: list[Path] = [Path(raw).expanduser()] if raw else []
    candidates.append(get_project_root() / "config.toml")
    for path in candidates:
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return digest[:48]
    return "no_config_file"
