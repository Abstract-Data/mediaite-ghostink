"""Interactive setup wizard for the forensics pipeline (Phase 12 §2).

This package provides a Textual-based TUI. The ``textual`` dependency ships as
an optional extra — install with ``uv sync --extra tui``. The module-level
``main()`` entry point is importable without textual, and will emit a friendly
install hint when the dependency is missing rather than crashing with a raw
``ImportError``.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Launch the TUI setup wizard.

    Returns an exit code (``0`` on clean exit, ``1`` when the ``tui`` extra is
    not installed). Designed to be used as the ``forensics-setup`` script entry
    point and from the ``forensics setup`` Typer command.
    """
    try:
        from forensics.tui.app import ForensicsSetupApp
    except ImportError as exc:
        # Top-level fallback — the only place a bare ``print`` is allowed per
        # the prompt. Message points the user at the documented install path.
        print(
            "forensics-setup requires the 'tui' extra.\n"
            "  Install with: uv sync --extra tui\n"
            f"  (import failure: {exc})",
            file=sys.stderr,
        )
        return 1

    app = ForensicsSetupApp()
    app.run()
    return 0


__all__ = ["main"]
