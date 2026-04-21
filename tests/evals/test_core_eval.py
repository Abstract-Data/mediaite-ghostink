"""Lightweight eval-style checks for Phase 1 contracts."""

from datetime import date

from forensics.cli import build_parser, main
from forensics.config import ForensicsSettings, get_settings
from forensics.models import Author


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
    parser = build_parser()
    for command in ("scrape", "extract", "analyze", "report", "all"):
        parsed = parser.parse_args([command])
        assert parsed.command == command


def test_eval_cli_main_stub(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["forensics", "all"])
    assert main() == 0
    assert "Phase not yet implemented" in capsys.readouterr().out
