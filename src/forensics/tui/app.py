"""Textual TUI application — multi-step setup wizard (Phase 12 §2d).

Five screens, navigated in order:

1. Dependencies — environment + model availability
2. Discovery   — author count (from ``articles.db`` or WordPress API)
3. Config      — generate ``config.toml``
4. Preflight   — re-run :func:`forensics.preflight.run_all_preflight_checks`
5. Launch      — confirm + emit recommended next CLI command

Navigation keybindings: ``q`` quit, ``n`` next, ``b`` back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App
from textual.binding import Binding

from forensics.tui.screens import (
    AuthorDiscoveryScreen,
    ConfigGenerationScreen,
    DependencyCheckScreen,
    PipelineLaunchScreen,
    PreflightScreen,
)


class ForensicsSetupApp(App):
    """Interactive setup wizard for AI Writing Forensics."""

    TITLE = "AI Writing Forensics — Setup Wizard"
    CSS_PATH = str(Path(__file__).with_name("styles.tcss"))
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("n", "next_step", "Next", show=True),
        Binding("b", "prev_step", "Back", show=True),
    ]

    SCREENS = {
        "dependencies": DependencyCheckScreen,
        "discovery": AuthorDiscoveryScreen,
        "config": ConfigGenerationScreen,
        "preflight": PreflightScreen,
        "launch": PipelineLaunchScreen,
    }

    STEP_ORDER: tuple[str, ...] = (
        "dependencies",
        "discovery",
        "config",
        "preflight",
        "launch",
    )

    def __init__(self) -> None:
        super().__init__()
        self._current_step: int = 0
        # Wizard-wide mutable state shared across screens. Typed loosely on
        # purpose — individual screens read/write their own keys.
        self.wizard_state: dict[str, Any] = {}

    def on_mount(self) -> None:
        """Push the first screen when the app mounts."""
        self.push_screen(self.STEP_ORDER[0])

    def action_next_step(self) -> None:
        if self._current_step < len(self.STEP_ORDER) - 1:
            self._current_step += 1
            self.push_screen(self.STEP_ORDER[self._current_step])

    def action_prev_step(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self.pop_screen()


__all__ = ["ForensicsSetupApp"]
