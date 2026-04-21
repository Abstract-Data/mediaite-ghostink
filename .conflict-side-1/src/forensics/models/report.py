"""Report generation manifests (stub for later phases)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReportManifest(BaseModel):
    run_id: str
    title: str
    generated_at: datetime
    sections: list[str]
    output_paths: dict[str, str]
