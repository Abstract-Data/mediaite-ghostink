"""Structured CLI failures — JSON envelope or stderr, then semantic exit code."""

from __future__ import annotations

import logging

import typer

from forensics.cli._envelope import emit, failure
from forensics.cli._exit import ExitCode
from forensics.cli.state import get_cli_state

logger = logging.getLogger(__name__)


def fail(
    ctx: typer.Context | None,
    cmd: str,
    code: str,
    message: str,
    *,
    exit_code: ExitCode = ExitCode.GENERAL_ERROR,
    suggestion: str | None = None,
    **extra: object,
) -> typer.Exit:
    """Emit a structured failure and return a :class:`typer.Exit` ready to ``raise``."""
    state = get_cli_state(ctx)
    if state.output_format == "json":
        emit(failure(cmd, code, message, suggestion=suggestion, **extra))
    else:
        prefix = f"ERROR ({code}): {message}"
        typer.echo(prefix, err=True)
        if suggestion:
            typer.echo(f"  → {suggestion}", err=True)
        if extra:
            for k, v in extra.items():
                typer.echo(f"  {k}: {v}", err=True)
    logger.error("%s: %s (%s)", cmd, message, code)
    return typer.Exit(code=int(exit_code))
