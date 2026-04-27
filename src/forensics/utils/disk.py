"""Disk space helpers (I-05)."""

from __future__ import annotations

import shutil
from pathlib import Path


def free_disk_bytes(path: Path) -> int:
    """Return free bytes on the filesystem containing ``path``."""
    usage = shutil.disk_usage(path.resolve())
    return int(usage.free)


def ensure_min_free_disk_bytes(path: Path, min_free: int, *, label: str = "disk") -> None:
    """Raise ``OSError`` when fewer than ``min_free`` bytes are available."""
    free = free_disk_bytes(path)
    if free < min_free:
        msg = f"{label}: need at least {min_free} free bytes on {path}, found {free}"
        raise OSError(msg)
