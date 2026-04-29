"""``forensics config audit`` smoke tests."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from forensics.cli import app
from forensics.config import get_settings


def test_config_audit_ok_on_defaults(forensics_config_path: object) -> None:
    """Minimal fixture config keeps analysis at defaults."""
    runner = CliRunner()
    result = runner.invoke(app, ["config", "audit"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "matches defaults" in result.output


def test_config_audit_json(forensics_config_path: object) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["config", "audit", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    data = json.loads(result.stdout.strip())
    assert data["non_default_fields"] == []
    assert data["count"] == 0


def test_config_audit_lists_override(
    forensics_config_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from forensics.config.analysis_settings import apply_flat_analysis_overrides
    from forensics.config.settings import ForensicsSettings

    base = get_settings()
    tweaked = base.model_copy(
        update={"analysis": apply_flat_analysis_overrides(base.analysis, pelt_penalty=99.0)}
    )

    def _fake_settings() -> ForensicsSettings:
        return tweaked

    monkeypatch.setattr("forensics.cli.config_cmd.get_settings", _fake_settings)
    runner = CliRunner()
    result = runner.invoke(app, ["config", "audit"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "pelt_penalty" in result.output
    assert "99" in result.output
