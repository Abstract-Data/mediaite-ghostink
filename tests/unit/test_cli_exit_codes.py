"""CLI semantic exit codes for TUI, lock, and headless gates (Item 8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import forensics.config as forensics_config
import forensics.preregistration as preregistration
from forensics.cli import app


def test_non_interactive_setup_exits_usage_error() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["--non-interactive", "setup"], color=False)
    assert r.exit_code == 2
    assert "ERROR (tty_required):" in (r.stderr or "")


def test_non_interactive_dashboard_exits_usage_error() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["--non-interactive", "dashboard"], color=False)
    assert r.exit_code == 2
    assert "tty_required" in (r.stderr or "")


def test_non_interactive_json_setup_failure_envelope() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["--non-interactive", "--output", "json", "setup"], color=False)
    assert r.exit_code == 2
    body = json.loads((r.stdout or "").strip())
    assert body["ok"] is False
    assert body["error"]["code"] == "tty_required"


def test_lock_preregistration_conflict_without_yes(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(forensics_config, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(preregistration, "get_project_root", lambda: tmp_path)
    lock_dir = tmp_path / "data" / "preregistration"
    lock_dir.mkdir(parents=True)
    (lock_dir / "preregistration_lock.json").write_text('{"locked_at": "x"}', encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(app, ["lock-preregistration"], color=False)
    assert r.exit_code == 5
    assert "lock_exists" in (r.stderr or "")


def test_lock_preregistration_yes_overwrites(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(forensics_config, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(preregistration, "get_project_root", lambda: tmp_path)
    lock_dir = tmp_path / "data" / "preregistration"
    lock_dir.mkdir(parents=True)
    (lock_dir / "preregistration_lock.json").write_text('{"locked_at": "old"}', encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(app, ["--yes", "lock-preregistration"], color=False)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    raw = json.loads((lock_dir / "preregistration_lock.json").read_text(encoding="utf-8"))
    assert raw.get("analysis") is not None
