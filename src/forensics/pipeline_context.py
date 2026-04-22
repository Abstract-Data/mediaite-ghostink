"""Shared paths and ``analysis_runs`` audit for CLI stages (non-scrape)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from forensics.config import get_project_root
from forensics.config.fingerprint import config_fingerprint
from forensics.storage.repository import insert_analysis_run

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineContext:
    """Resolved project layout and config fingerprint for pipeline audit."""

    root: Path
    db_path: Path
    config_hash: str

    @classmethod
    def resolve(cls) -> PipelineContext:
        root = get_project_root()
        return cls(
            root=root,
            db_path=root / "data" / "articles.db",
            config_hash=config_fingerprint(),
        )

    def record_audit(
        self,
        description: str,
        *,
        optional: bool = False,
        log: logging.Logger | None = None,
    ) -> str | None:
        """Insert an ``analysis_runs`` row and log a single audit line.

        When ``optional`` is True, ``OSError`` from SQLite open/write is logged
        and ``None`` is returned (matches extract / ``forensics all`` behavior).
        When ``optional`` is False, errors propagate (matches analyze paths
        that embed ``run_id`` into ``run_metadata.json``).
        """
        lg = log or logger
        if optional:
            try:
                rid = insert_analysis_run(
                    self.db_path,
                    config_hash=self.config_hash,
                    description=description,
                )
            except OSError as exc:
                lg.warning("Could not record analysis_runs row: %s", exc)
                return None
        else:
            rid = insert_analysis_run(
                self.db_path,
                config_hash=self.config_hash,
                description=description,
            )
        lg.info(
            "pipeline audit: run_id=%s description=%s config_fingerprint=%s",
            rid,
            description,
            self.config_hash[:12],
        )
        return rid
