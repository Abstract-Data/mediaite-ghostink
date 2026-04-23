"""TUI wizard screens (Phase 12 §2j)."""

from __future__ import annotations

from forensics.tui.screens.config import ConfigGenerationScreen
from forensics.tui.screens.dependencies import DependencyCheckScreen
from forensics.tui.screens.discovery import AuthorDiscoveryScreen
from forensics.tui.screens.launch import PipelineLaunchScreen
from forensics.tui.screens.preflight import PreflightScreen

__all__ = [
    "AuthorDiscoveryScreen",
    "ConfigGenerationScreen",
    "DependencyCheckScreen",
    "PipelineLaunchScreen",
    "PreflightScreen",
]
