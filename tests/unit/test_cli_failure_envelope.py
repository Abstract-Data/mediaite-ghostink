"""Structured ``fail()`` envelopes for ``forensics validate`` (Item 6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from forensics.cli import app
from forensics.config import get_settings


def test_validate_malformed_config_json_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = tmp_path / "config.toml"
    bad.write_text("[[authors\nnot valid toml", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(bad))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        r = runner.invoke(app, ["--output", "json", "validate"], color=False)
        assert r.exit_code == 2, (r.stdout, r.stderr)
        out = (r.stdout or "").strip()
        body = json.loads(out)
        assert body["ok"] is False
        assert body["type"] == "validate"
        assert body["error"]["code"] == "config_invalid"
        assert body["error"]["suggestion"]
    finally:
        monkeypatch.delenv("FORENSICS_CONFIG_FILE", raising=False)
        get_settings.cache_clear()


def test_validate_malformed_config_text_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = tmp_path / "config.toml"
    bad.write_text("[[authors\nnot valid toml", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(bad))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        r = runner.invoke(app, ["validate"], color=False)
        assert r.exit_code == 2
        err = r.stderr or ""
        assert "ERROR (config_invalid):" in err
        assert "→" in err or "run: forensics preflight" in err
    finally:
        monkeypatch.delenv("FORENSICS_CONFIG_FILE", raising=False)
        get_settings.cache_clear()
