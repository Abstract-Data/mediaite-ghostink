"""Tests for ``forensics peer-setup``."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import MINIMAL_CONFIG_TOML
from typer.testing import CliRunner

from forensics.cli import app
from forensics.config import get_settings


def test_peer_setup_prints_ollama_pull_for_baseline_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        MINIMAL_CONFIG_TOML.strip() + "\n[baseline]\n"
        'models = ["fixture-ollama-one", "fixture-ollama-two"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(app, ["peer-setup"], color=False)
        assert result.exit_code == 0, (result.stdout, result.stderr)
        out = result.stdout or ""
        assert "ollama pull fixture-ollama-one" in out
        assert "ollama pull fixture-ollama-two" in out
        assert "uv sync --extra dev --extra tui" in out
    finally:
        get_settings.cache_clear()
