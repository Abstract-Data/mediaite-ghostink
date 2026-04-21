"""Lightweight eval-style checks for Phase 1 contracts."""

from __future__ import annotations

from datetime import date

from typer.testing import CliRunner

from forensics.cli import app, main
from forensics.config import ForensicsSettings, get_settings
from forensics.models import Author

_runner = CliRunner()


def test_eval_settings_contract(monkeypatch) -> None:
    monkeypatch.delenv("FORENSICS_CONFIG_FILE", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert isinstance(settings, ForensicsSettings)
    assert len(settings.authors) >= 1
    get_settings.cache_clear()


def test_eval_models_import_contract() -> None:
    author = Author(
        name="Eval Author",
        slug="eval-author",
        outlet="mediaite.com",
        role="control",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2021, 1, 1),
        archive_url="https://www.mediaite.com/author/eval/",
    )
    assert author.slug == "eval-author"


def test_eval_cli_stage_command_regression() -> None:
    for command in ("scrape", "extract", "analyze", "report", "all"):
        result = _runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, f"{command} --help failed: {result.output}"


def test_eval_cli_main_entrypoint_returns_int(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["forensics", "--help"])
    rc = main()
    assert isinstance(rc, int)
