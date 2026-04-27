"""Launch screen: confirms and prints the next CLI command (does not run the pipeline)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Label, Static


class PipelineLaunchScreen(Screen):
    """Screen 5: confirmation + pick the next CLI command to run."""

    def compose(self) -> ComposeResult:
        yield Label("Step 5 of 5: Launch Pipeline", id="step-label")
        yield Static("Setup complete. Choose the next command to run:", id="status")
        yield Button("Run blind survey (forensics survey)", id="survey-btn", variant="primary")
        yield Button("Run full pipeline (forensics all)", id="all-btn", variant="default")
        yield Button("Exit without launching", id="exit-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "survey-btn":
            self._emit_and_exit("forensics survey")
        elif event.button.id == "all-btn":
            self._emit_and_exit("forensics all")
        elif event.button.id == "exit-btn":
            self._emit_and_exit(None)

    def _emit_and_exit(self, command: str | None) -> None:
        # Stash the chosen command so ``main()`` can print it after the app
        # exits. The actual message is surfaced in the terminal below.
        state = self.app.wizard_state
        state["next_command"] = command
        if command:
            self.app.exit(message=f"Run next: {command}")
        else:
            self.app.exit(message="Setup complete — no command launched.")


__all__ = ["PipelineLaunchScreen"]
