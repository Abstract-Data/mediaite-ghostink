"""Preflight screen wrapping :func:`forensics.preflight.run_all_preflight_checks`."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label, Static

logger = logging.getLogger(__name__)

_ICONS: dict[str, str] = {
    "pass": "OK",
    "warn": "WARN",
    "fail": "FAIL",
}


class PreflightScreen(Screen):
    """Screen 4: run all preflight checks and summarise results."""

    def compose(self) -> ComposeResult:
        yield Label("Step 4 of 5: Preflight Validation", id="step-label")
        yield Static("Running preflight checks...", id="status")
        yield DataTable(id="preflight-table")
        yield Button("Re-run", id="run-btn", variant="default")
        yield Button("Continue (n)", id="next-btn", variant="success", disabled=True)

    def on_mount(self) -> None:
        table = self.query_one("#preflight-table", DataTable)
        table.add_columns("Check", "Status", "Detail")
        self._run_preflight()

    def _run_preflight(self) -> None:
        from forensics.preflight import run_all_preflight_checks

        table = self.query_one("#preflight-table", DataTable)
        table.clear()

        settings = None
        try:
            from forensics.config import get_settings

            settings = get_settings()
        except Exception as exc:  # noqa: BLE001 - preflight will still surface
            logger.warning("preflight: could not load settings: %s", exc)

        report = run_all_preflight_checks(settings)
        for check in report.checks:
            table.add_row(check.name, _ICONS[check.status], check.message)

        status = self.query_one("#status", Static)
        next_btn = self.query_one("#next-btn", Button)
        if report.has_failures:
            status.update(f"{len(report.failures())} required check(s) failed — fix before launch.")
            next_btn.disabled = True
        elif report.has_warnings:
            status.update("All required checks passed (some warnings).")
            next_btn.disabled = False
        else:
            status.update("All preflight checks passed.")
            next_btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self._run_preflight()
        elif event.button.id == "next-btn":
            self.app.action_next_step()


__all__ = ["PreflightScreen"]
