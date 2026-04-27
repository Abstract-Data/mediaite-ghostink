"""Shared CLI state attached to Typer ``Context.obj``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import typer


@dataclass
class ForensicsCliState:
    """Root options on ``Context.obj`` (JSON output disables progress in the root callback)."""

    show_progress: bool = True
    output_format: Literal["text", "json"] = "text"
    non_interactive: bool = False
    assume_yes: bool = False


def get_cli_state(ctx: typer.Context | None) -> ForensicsCliState:
    """Return ``ForensicsCliState`` from the context chain, or defaults."""
    cur: typer.Context | None = ctx
    while cur is not None:
        obj = getattr(cur, "obj", None)
        if isinstance(obj, ForensicsCliState):
            return obj
        cur = cast(typer.Context | None, cur.parent)
    return ForensicsCliState()
