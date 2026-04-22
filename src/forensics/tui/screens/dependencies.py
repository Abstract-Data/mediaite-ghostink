"""Dependency check screen (Phase 12 §2e).

Surfaces environment readiness: Python version, spaCy model, sentence-
transformers, Quarto, Ollama. Core logic lives in :func:`check_dependencies`
so the data model is unit-testable without a running Textual app.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label, Static

logger = logging.getLogger(__name__)

DependencyStatus = Literal["pass", "warn", "fail"]

_ICONS: dict[DependencyStatus, str] = {
    "pass": "OK",
    "warn": "WARN",
    "fail": "FAIL",
}


@dataclass(frozen=True)
class DependencyCheckResult:
    """One dependency probe result (immutable, easy to snapshot in tests)."""

    name: str
    required: bool
    status: DependencyStatus
    version: str
    install_hint: str

    @property
    def is_blocker(self) -> bool:
        """True when the dependency is required and did not pass."""
        return self.required and self.status == "fail"


# ---------------------------------------------------------------------------
# Individual probes — each returns a :class:`DependencyCheckResult`.
# ---------------------------------------------------------------------------


def _check_python() -> DependencyCheckResult:
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 13)
    return DependencyCheckResult(
        name="Python 3.13+",
        required=True,
        status="pass" if ok else "fail",
        version=py_ver,
        install_hint="Install Python 3.13 via pyenv or brew",
    )


def _check_spacy_model(model_name: str = "en_core_web_sm") -> DependencyCheckResult:
    try:
        import spacy
    except ImportError:
        return DependencyCheckResult(
            name=f"spaCy {model_name}",
            required=True,
            status="fail",
            version="not importable",
            install_hint="uv sync  # ensures spacy is installed",
        )
    try:
        nlp = spacy.load(model_name)
    except OSError:
        return DependencyCheckResult(
            name=f"spaCy {model_name}",
            required=True,
            status="fail",
            version="not downloaded",
            install_hint=f"uv run python -m spacy download {model_name}",
        )
    version = nlp.meta.get("version", "?") if getattr(nlp, "meta", None) else "?"
    return DependencyCheckResult(
        name=f"spaCy {model_name}",
        required=True,
        status="pass",
        version=str(version),
        install_hint="",
    )


def _check_sentence_transformers() -> DependencyCheckResult:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return DependencyCheckResult(
            name="sentence-transformers",
            required=True,
            status="fail",
            version="not importable",
            install_hint="uv sync",
        )
    # Cache present? Not strictly required — model auto-downloads on first
    # use, so treat missing cache as ``warn``.
    cache_dir = Path.home() / ".cache" / "torch" / "sentence_transformers"
    cached = cache_dir.exists() and any(cache_dir.glob("*MiniLM*"))
    return DependencyCheckResult(
        name="all-MiniLM-L6-v2",
        required=True,
        status="pass" if cached else "warn",
        version="cached" if cached else "will download (~80MB)",
        install_hint="" if cached else "Auto-downloads on first use",
    )


def _check_quarto() -> DependencyCheckResult:
    path = shutil.which("quarto")
    if path is None:
        return DependencyCheckResult(
            name="Quarto",
            required=False,
            status="warn",
            version="not found",
            install_hint="brew install quarto  # or https://quarto.org/docs/get-started/",
        )
    return DependencyCheckResult(
        name="Quarto",
        required=False,
        status="pass",
        version=_safe_version(path, "--version"),
        install_hint="",
    )


def _check_ollama() -> DependencyCheckResult:
    path = shutil.which("ollama")
    if path is None:
        return DependencyCheckResult(
            name="Ollama",
            required=False,
            status="warn",
            version="not found",
            install_hint="brew install ollama  # optional (AI baseline)",
        )
    return DependencyCheckResult(
        name="Ollama",
        required=False,
        status="pass",
        version=_safe_version(path, "--version"),
        install_hint="",
    )


def _safe_version(cmd: str, flag: str, timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            [cmd, flag],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    out = (result.stdout or result.stderr or "").strip().splitlines()
    return out[0] if out else "unknown"


def check_dependencies() -> list[DependencyCheckResult]:
    """Probe every dependency the wizard cares about.

    Each probe is independent — one failure never blocks the others. The
    returned list preserves a stable, user-facing order (required first).
    """
    return [
        _check_python(),
        _check_spacy_model(),
        _check_sentence_transformers(),
        _check_quarto(),
        _check_ollama(),
    ]


def has_blocking_failures(results: list[DependencyCheckResult]) -> bool:
    """True when any required dependency failed (cannot proceed)."""
    return any(r.is_blocker for r in results)


# ---------------------------------------------------------------------------
# Textual Screen — assembles the table view and Next button.
# ---------------------------------------------------------------------------


class DependencyCheckScreen(Screen):
    """Screen 1: run dependency checks and show a table of pass/warn/fail."""

    def compose(self) -> ComposeResult:
        yield Label("Step 1 of 5: Dependency Check", id="step-label")
        yield Static("Checking required tools and models...", id="status")
        yield DataTable(id="dep-table")
        yield Button("Continue (n)", id="next-btn", variant="success", disabled=True)

    def on_mount(self) -> None:
        table = self.query_one("#dep-table", DataTable)
        table.add_columns("Dependency", "Required", "Status", "Version", "Fix")
        results = check_dependencies()
        for r in results:
            table.add_row(
                r.name,
                "required" if r.required else "optional",
                _ICONS[r.status],
                r.version,
                r.install_hint,
            )

        status = self.query_one("#status", Static)
        next_btn = self.query_one("#next-btn", Button)
        if has_blocking_failures(results):
            blockers = [r.name for r in results if r.is_blocker]
            status.update(f"Blocked: {', '.join(blockers)}")
            next_btn.disabled = True
        else:
            status.update("All required dependencies installed.")
            next_btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next-btn":
            self.app.action_next_step()


__all__ = [
    "DependencyCheckResult",
    "DependencyCheckScreen",
    "DependencyStatus",
    "check_dependencies",
    "has_blocking_failures",
]
