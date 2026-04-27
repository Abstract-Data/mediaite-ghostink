"""Shared CLI state attached to Typer ``Context.obj``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import typer


@dataclass
class ForensicsCliState:
    """Root ``forensics`` options visible to subcommands via :func:`get_cli_state`.

    When ``output_format == \"json\"``, ``show_progress`` is forced to ``False`` at
    the root callback so Rich progress does not write to stderr during agent runs.
    """

    show_progress: bool = True
    output_format: Literal["text", "json"] = "text"
    non_interactive: bool = False
    assume_yes: bool = False


def get_cli_state(ctx: typer.Context | None) -> ForensicsCliState:
    """Walk the Typer/Click context chain for :class:`ForensicsCliState` (default if missing)."""
    cur: typer.Context | None = ctx
    while cur is not None:
        obj = getattr(cur, "obj", None)
        if isinstance(obj, ForensicsCliState):
            return obj
        cur = cur.parent  # type: ignore[assignment]
    return ForensicsCliState()
