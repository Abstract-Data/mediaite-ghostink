"""Test Typer CLI accepts all stage commands and flags."""

import re

from typer.testing import CliRunner

from forensics.cli import app

runner = CliRunner()
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _plain(text: str) -> str:
    """Rich styles break contiguous substrings (e.g. ``--flag``); strip for assertions."""
    return _ANSI_ESCAPE.sub("", text)


def test_cli_help_exits_cleanly() -> None:
    result = runner.invoke(app, ["--help"], color=False)
    assert result.exit_code == 0
    assert "forensics" in result.output.lower() or "pipeline" in result.output.lower()


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"], color=False)
    assert result.exit_code == 0
    assert "forensics" in result.output


def test_scrape_help() -> None:
    result = runner.invoke(app, ["scrape", "--help"], color=False)
    assert result.exit_code == 0
    out = _plain(result.output)
    for flag in ("--discover", "--metadata", "--fetch", "--dedup", "--archive", "--dry-run"):
        assert flag in out


def test_extract_help() -> None:
    result = runner.invoke(app, ["extract", "--help"], color=False)
    assert result.exit_code == 0
    out = _plain(result.output)
    for flag in (
        "--author",
        "--skip-embeddings",
        "--skip-probability",
        "--probability",
        "--no-binoculars",
        "--device",
    ):
        assert flag in out


def test_analyze_help() -> None:
    result = runner.invoke(app, ["analyze", "--help"], color=False)
    assert result.exit_code == 0
    out = _plain(result.output)
    for flag in (
        "--changepoint",
        "--timeseries",
        "--drift",
        "--convergence",
        "--compare",
        "--ai-baseline",
        "--author",
        "--verify-corpus",
        "--openai-key",
        "--llm-model",
    ):
        assert flag in out


def test_report_help() -> None:
    result = runner.invoke(app, ["report", "--help"], color=False)
    assert result.exit_code == 0
    out = _plain(result.output)
    for flag in ("--notebook", "--format", "--verify"):
        assert flag in out


def test_all_help() -> None:
    result = runner.invoke(app, ["all", "--help"], color=False)
    assert result.exit_code == 0
