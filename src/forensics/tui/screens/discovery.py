"""Author discovery screen (Phase 12 §2f).

Shows how many authors are already in ``articles.db`` (via
:meth:`Repository.all_authors`) and lets the user pick between
blind-survey and hand-pick modes. Writes the choice into
``app.wizard_state`` so the config generation screen can use it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Label, RadioButton, RadioSet, Static

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthorDiscoveryResult:
    """Summary of author discovery (used by the config screen)."""

    db_exists: bool
    author_count: int
    source: str  # "database" | "empty" | "missing"
    db_path: Path


def discover_authors_summary(db_path: Path) -> AuthorDiscoveryResult:
    """Probe ``articles.db`` and return a structured summary.

    Falls back gracefully when the database does not exist yet — the TUI is
    meant to run *before* the first scrape, so an empty or missing DB is
    expected on a fresh install.
    """
    if not db_path.is_file():
        return AuthorDiscoveryResult(
            db_exists=False,
            author_count=0,
            source="missing",
            db_path=db_path,
        )

    try:
        from forensics.storage.repository import Repository

        with Repository(db_path) as repo:
            authors = repo.all_authors()
        return AuthorDiscoveryResult(
            db_exists=True,
            author_count=len(authors),
            source="database" if authors else "empty",
            db_path=db_path,
        )
    except Exception as exc:  # noqa: BLE001 - surface any repo error as empty
        logger.warning("discovery: repository probe failed: %s", exc)
        return AuthorDiscoveryResult(
            db_exists=True,
            author_count=0,
            source="empty",
            db_path=db_path,
        )


class AuthorDiscoveryScreen(Screen):
    """Screen 2: summarise author inventory and pick survey mode."""

    def compose(self) -> ComposeResult:
        yield Label("Step 2 of 5: Author Discovery", id="step-label")
        yield Static("Probing articles.db for discovered authors...", id="status")
        yield RadioSet(
            RadioButton("Blind survey (analyse every qualified author)", id="mode-blind"),
            RadioButton("Hand-pick target/control authors", id="mode-pick"),
            id="mode-group",
        )
        yield Button("Continue (n)", id="next-btn", variant="success")

    def on_mount(self) -> None:
        from forensics.config import get_project_root

        db_path = get_project_root() / "data" / "articles.db"
        summary = discover_authors_summary(db_path)

        status = self.query_one("#status", Static)
        if summary.source == "missing":
            status.update(
                "No articles.db yet — blind survey will discover authors from "
                "the WordPress API when you run `forensics scrape`."
            )
        elif summary.source == "empty":
            status.update(
                f"articles.db found at {summary.db_path} but contains no authors yet. "
                "Run `forensics scrape` after setup to populate."
            )
        else:
            status.update(
                f"Found {summary.author_count} author(s) in articles.db. Pick survey mode below."
            )

        # Default to blind mode — set value on the RadioButton (pressed_button
        # is a read-only property in Textual 8.x).
        blind_btn = self.query_one("#mode-blind", RadioButton)
        blind_btn.value = True
        self.app.wizard_state["mode"] = "blind"
        self.app.wizard_state["author_count"] = summary.author_count

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        button_id = event.pressed.id or "mode-blind"
        self.app.wizard_state["mode"] = "blind" if button_id == "mode-blind" else "pick"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next-btn":
            self.app.action_next_step()


__all__ = [
    "AuthorDiscoveryResult",
    "AuthorDiscoveryScreen",
    "discover_authors_summary",
]
