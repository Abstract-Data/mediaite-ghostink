"""Interactive setup wizard for the forensics pipeline (Phase 12 §2).

This package provides a Textual-based TUI. The ``textual`` dependency ships as
an optional extra — install with ``uv sync --extra tui``. The module-level
``main()`` entry point is importable without textual, and will emit a friendly
install hint when the dependency is missing rather than crashing with a raw
``ImportError``.
"""

from __future__ import annotations

import typer


def main() -> int:
    """Launch the TUI setup wizard.

    Returns an exit code (``0`` on clean exit, ``1`` when the ``tui`` extra is
    not installed). Designed to be used as the ``forensics-setup`` script entry
    point and from the ``forensics setup`` Typer command.
    """
    try:
        from forensics.tui.app import ForensicsSetupApp
    except ImportError as exc:
        typer.echo(
            "forensics-setup requires the 'tui' extra.\n"
            "  Install with: uv sync --extra tui\n"
            f"  (import failure: {exc})",
            err=True,
        )
        return 1

    app = ForensicsSetupApp()
    app.run()
    return 0


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
        return 1

    return run_dashboard_interactive(survey_mode=survey_mode, survey_kwargs=survey_kwargs)


__all__ = ["main", "main_dashboard"]
