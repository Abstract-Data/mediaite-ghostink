"""Typed CLI/report interface (replaces argparse.Namespace)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReportArgs(BaseModel):
    """Arguments for Quarto report rendering."""

    notebook: str | None = None
    report_format: str = Field(default="both", description="html, pdf, or both")
    verify: bool = False
