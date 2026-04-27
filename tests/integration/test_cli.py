"""Test Typer CLI accepts all stage commands and flags."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from forensics.cli import app

runner = CliRunner()


def _plain_help(output: str) -> str:
    """Rich/Typer help uses ANSI sequences; strip them for substring assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", output)


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
    text = _plain_help(result.output)
    for flag in (
        "--discover",
        "--metadata",
        "--fetch",
        "--dedup",
        "--archive",
        "--dry-run",
        "--force-refresh",
        "--all-authors",
    ):
        assert flag in text, f"missing {flag} in scrape help"


def test_extract_help_lists_flags() -> None:
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    for flag in (
        "--author",
        "--skip-embeddings",
        "--probability",
        "--no-binoculars",
        "--device",
    ):
        assert flag in text, f"missing {flag} in extract help"


def test_analyze_help_lists_flags() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
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
        "--exploratory",
        "--max-workers",
        "--parallel-authors",
    ):
        assert flag in text, f"missing {flag} in analyze help"


def test_report_help_lists_flags() -> None:
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    for flag in ("--notebook", "--format", "--verify"):
        assert flag in text, f"missing {flag} in report help"


def test_all_help_exits_cleanly() -> None:
    result = runner.invoke(app, ["all", "--help"])
    assert result.exit_code == 0


def test_analyze_verify_corpus_fails_on_missing_custody(
    tmp_path, forensics_config_path, monkeypatch
) -> None:
    """`analyze --verify-corpus` must exit AUTH_OR_RESOURCE (3) when custody is absent."""
    import importlib

    analyze_mod = importlib.import_module("forensics.cli.analyze")
    from forensics.storage.repository import init_db

    init_db(tmp_path / "data" / "articles.db")
    monkeypatch.setattr(analyze_mod, "get_project_root", lambda: tmp_path)
    result = runner.invoke(app, ["analyze", "--verify-corpus", "--author", "fixture-author"])
    assert result.exit_code == 3


def test_analyze_verify_corpus_passes_on_matching_custody(
    tmp_path, forensics_config_path, monkeypatch
) -> None:
    """Matching corpus_custody.json should let `--verify-corpus` proceed past the check."""
    import importlib

    from forensics.analysis import orchestrator as orch_mod

    analyze_mod = importlib.import_module("forensics.cli.analyze")
    from forensics.storage.repository import init_db
    from forensics.utils.provenance import write_corpus_custody

    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    analysis_dir = tmp_path / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    write_corpus_custody(db_path, analysis_dir)
    monkeypatch.setattr(analyze_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "forensics.pipeline_context.insert_analysis_run",
        lambda *a, **kw: "run-id",
    )
    # --compare short-circuits analyze after verify; stub the comparison to skip real work.
    monkeypatch.setattr(orch_mod, "run_compare_only", lambda *a, **kw: None)

    result = runner.invoke(
        app,
        [
            "analyze",
            "--verify-corpus",
            "--compare",
            "--author",
            "fixture-author",
            "--exploratory",
        ],
    )
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Phase 12 §7 — validate + export CLI coverage
# ---------------------------------------------------------------------------


def test_validate_help() -> None:
    result = runner.invoke(app, ["validate", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    assert "--check-endpoints" in text


def test_validate_config_command(forensics_config_path, monkeypatch) -> None:
    """Valid config + preflight should exit 0 (warns are allowed, fails are not)."""
    import forensics.preflight as preflight_mod
    from forensics.preflight import PreflightCheck, PreflightReport

    # ``validate`` imports ``run_all_preflight_checks`` lazily from ``forensics.preflight``,
    # so patching the source module is sufficient — no need to also patch ``forensics.cli``.
    monkeypatch.setattr(
        preflight_mod,
        "run_all_preflight_checks",
        lambda *_a, **_kw: PreflightReport(
            checks=(
                PreflightCheck("Config file", "pass", "ok"),
                PreflightCheck("Python version", "pass", "3.13"),
            )
        ),
    )

    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "Config parsed" in result.output
    assert "All validation checks passed" in result.output or "warnings" in result.output


def test_validate_detects_config_error(tmp_path, monkeypatch) -> None:
    """An unparseable config.toml should make ``validate`` exit USAGE_ERROR (2)."""
    bad_cfg = tmp_path / "config.toml"
    bad_cfg.write_text("this is = not valid = toml [[[\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(bad_cfg))
    from forensics.config import get_settings

    get_settings.cache_clear()
    try:
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "Config error" in combined
    finally:
        get_settings.cache_clear()


def test_export_help() -> None:
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    assert "--output" in text
    assert "--no-features" in text
    assert "--no-analysis" in text


def test_export_to_duckdb_smoke(tmp_path, sample_author, sample_article) -> None:
    """Seed SQLite via Repository, run export, verify both tables exist with row counts."""
    import duckdb

    from forensics.storage.duckdb_queries import export_to_duckdb
    from forensics.storage.repository import Repository

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "articles.db"

    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)

    out_path = tmp_path / "forensics_export.duckdb"
    report = export_to_duckdb(db_path, out_path, include_features=False, include_analysis=False)

    assert report.output_path == out_path
    assert report.bytes_written > 0
    assert report.tables == {"authors": 1, "articles": 1}
    assert out_path.is_file()

    conn = duckdb.connect(str(out_path), read_only=True)
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert {"authors", "articles"}.issubset(tables)
        assert conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Phase 12 §10 — survey / calibrate / preflight / lock / setup CLI surface
# ---------------------------------------------------------------------------


def test_survey_help_lists_flags() -> None:
    result = runner.invoke(app, ["survey", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    for flag in (
        "--dry-run",
        "--resume",
        "--skip-scrape",
        "--author",
        "--min-articles",
        "--include-shared-bylines",
    ):
        assert flag in text, f"missing {flag} in survey help"


def test_calibrate_help_lists_flags() -> None:
    result = runner.invoke(app, ["calibrate", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    for flag in ("--positive-trials", "--negative-trials", "--author", "--dry-run"):
        assert flag in text, f"missing {flag} in calibrate help"


def test_preflight_help_lists_strict() -> None:
    result = runner.invoke(app, ["preflight", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    assert "--strict" in text


def test_lock_preregistration_help() -> None:
    result = runner.invoke(app, ["lock-preregistration", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    assert "lock" in text.lower() or "pre-registration" in text.lower()


def test_setup_help() -> None:
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    text = _plain_help(result.output)
    assert "setup" in text.lower() or "wizard" in text.lower()
