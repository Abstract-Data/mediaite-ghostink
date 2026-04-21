"""Test Typer CLI accepts all stage commands and flags."""

from __future__ import annotations

from typer.testing import CliRunner

from forensics.cli import app

runner = CliRunner()


def test_cli_help_exits_cleanly() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    assert "forensics" in output or "pipeline" in output


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "forensics" in result.output


def test_scrape_help_lists_flags() -> None:
    result = runner.invoke(app, ["scrape", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--discover",
        "--metadata",
        "--fetch",
        "--dedup",
        "--archive",
        "--dry-run",
        "--force-refresh",
    ):
        assert flag in result.output, f"missing {flag} in scrape help"


def test_extract_help_lists_flags() -> None:
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--author",
        "--skip-embeddings",
        "--probability",
        "--no-binoculars",
        "--device",
    ):
        assert flag in result.output, f"missing {flag} in extract help"


def test_analyze_help_lists_flags() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--changepoint",
        "--timeseries",
        "--drift",
        "--convergence",
        "--compare",
        "--ai-baseline",
        "--skip-generation",
        "--verify-corpus",
        "--author",
    ):
        assert flag in result.output, f"missing {flag} in analyze help"


def test_report_help_lists_flags() -> None:
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    for flag in ("--notebook", "--format", "--verify"):
        assert flag in result.output, f"missing {flag} in report help"


def test_all_help_exits_cleanly() -> None:
    result = runner.invoke(app, ["all", "--help"])
    assert result.exit_code == 0
