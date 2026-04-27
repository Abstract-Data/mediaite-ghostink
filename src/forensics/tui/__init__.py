"""Textual setup wizard (install with ``uv sync --extra tui``).

:func:`main` prints a hint if ``textual`` is missing instead of raising raw import errors.
"""

from __future__ import annotations

import typer

from forensics.cli._exit import ExitCode


def main() -> int:
    """Launch setup wizard; ``1`` if the ``tui`` extra is not installed."""
    try:
        from forensics.tui.app import ForensicsSetupApp
    except ImportError as exc:
        typer.echo(
            "forensics-setup requires the 'tui' extra.\n"
            "  Install with: uv sync --extra tui\n"
            f"  (import failure: {exc})",
            err=True,
        )
        return int(ExitCode.GENERAL_ERROR)

    app = ForensicsSetupApp()
    app.run()
    return int(ExitCode.OK)


def main_dashboard(
    *,
    survey_mode: bool = False,
    survey_kwargs: dict | None = None,
) -> int:
    """Launch the pipeline progress dashboard (requires the ``tui`` extra)."""
    try:
        from forensics.tui.pipeline_app import run_dashboard_interactive
    except ImportError as exc:
        typer.echo(
            "forensics dashboard requires the 'tui' extra.\n"
            "  Install with: uv sync --extra tui\n"
            f"  (import failure: {exc})",
            err=True,
        )
        return int(ExitCode.GENERAL_ERROR)

    return run_dashboard_interactive(survey_mode=survey_mode, survey_kwargs=survey_kwargs)


__all__ = ["main", "main_dashboard"]
