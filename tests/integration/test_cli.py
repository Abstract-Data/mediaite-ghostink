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


def test_analyze_verify_corpus_fails_on_missing_custody(
    tmp_path, forensics_config_path, monkeypatch
) -> None:
    """`analyze --verify-corpus` must exit 1 when the custody file is absent."""
    import importlib

    analyze_mod = importlib.import_module("forensics.cli.analyze")
    from forensics.storage.repository import init_db

    init_db(tmp_path / "data" / "articles.db")
    monkeypatch.setattr(analyze_mod, "get_project_root", lambda: tmp_path)
    result = runner.invoke(app, ["analyze", "--verify-corpus", "--author", "fixture-author"])
    assert result.exit_code == 1


def test_analyze_verify_corpus_passes_on_matching_custody(
    tmp_path, forensics_config_path, monkeypatch
) -> None:
    """Matching corpus_custody.json should let `--verify-corpus` proceed past the check."""
    import importlib
    import json

    from forensics.analysis import orchestrator as orch_mod

    analyze_mod = importlib.import_module("forensics.cli.analyze")
    from forensics.storage.repository import init_db
    from forensics.utils.provenance import compute_corpus_hash

    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    analysis_dir = tmp_path / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "corpus_custody.json").write_text(
        json.dumps({"corpus_hash": compute_corpus_hash(db_path)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(analyze_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(analyze_mod, "insert_analysis_run", lambda *a, **kw: "run-id")
    # --compare short-circuits analyze after verify; stub the comparison to skip real work.
    monkeypatch.setattr(orch_mod, "run_compare_only", lambda *a, **kw: None)

    result = runner.invoke(
        app, ["analyze", "--verify-corpus", "--compare", "--author", "fixture-author"]
    )
    assert result.exit_code == 0, result.output
