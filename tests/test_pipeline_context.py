"""Tests for :mod:`forensics.pipeline_context`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from forensics.pipeline_context import PipelineContext
from forensics.storage.repository import init_db


def test_record_audit_optional_inserts_row(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "forensics.pipeline_context.get_project_root",
        lambda: tmp_path,
    )
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)

    ctx = PipelineContext.resolve()
    rid = ctx.record_audit("unit test optional", optional=True)

    assert rid is not None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, description FROM analysis_runs WHERE id = ?",
            (rid,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[1] == "unit test optional"


def test_record_audit_optional_logs_on_oserror(tmp_path: Path, monkeypatch, caplog) -> None:
    import logging

    monkeypatch.setattr(
        "forensics.pipeline_context.get_project_root",
        lambda: tmp_path,
    )
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def boom(*_a, **_kw):
        raise OSError("no db")

    monkeypatch.setattr("forensics.pipeline_context.insert_analysis_run", boom)
    caplog.set_level(logging.WARNING)

    ctx = PipelineContext.resolve()
    assert ctx.record_audit("x", optional=True) is None
    assert "Could not record analysis_runs row" in caplog.text


def test_record_audit_required_propagates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "forensics.pipeline_context.get_project_root",
        lambda: tmp_path,
    )
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def boom(*_a, **_kw):
        raise OSError("denied")

    monkeypatch.setattr("forensics.pipeline_context.insert_analysis_run", boom)
    ctx = PipelineContext.resolve()

    try:
        ctx.record_audit("x", optional=False)
    except OSError as exc:
        assert "denied" in str(exc)
    else:
        raise AssertionError("expected OSError")


def test_config_fingerprint_returns_none_when_no_config(tmp_path: Path, monkeypatch) -> None:
    """Without config.toml and FORENSICS_CONFIG_FILE, fingerprint is None (not a sentinel)."""
    from forensics.config.fingerprint import config_fingerprint

    monkeypatch.delenv("FORENSICS_CONFIG_FILE", raising=False)
    monkeypatch.setattr(
        "forensics.config.fingerprint.get_project_root",
        lambda: tmp_path,
    )
    assert config_fingerprint() is None


def test_record_audit_skips_row_when_fingerprint_none(tmp_path: Path, monkeypatch, caplog) -> None:
    """When fingerprint is None, no analysis_runs row is written (NOT NULL schema preserved)."""
    import logging

    monkeypatch.delenv("FORENSICS_CONFIG_FILE", raising=False)
    monkeypatch.setattr(
        "forensics.pipeline_context.get_project_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "forensics.config.fingerprint.get_project_root",
        lambda: tmp_path,
    )
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)

    caplog.set_level(logging.WARNING)
    ctx = PipelineContext.resolve()
    assert ctx.config_hash is None
    rid = ctx.record_audit("no-config run", optional=True)

    assert rid is None
    assert "pipeline audit skipped" in caplog.text

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_resolve_accepts_explicit_root(tmp_path: Path, monkeypatch) -> None:
    """Callers that already resolved ``root`` can avoid a second ``get_project_root`` lookup."""
    monkeypatch.setattr(
        "forensics.pipeline_context.get_project_root",
        lambda: (_ for _ in ()).throw(AssertionError("get_project_root should not be called")),
    )
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(tmp_path / "config.toml"))
    (tmp_path / "config.toml").write_text("[scraping]\nrate_limit_seconds = 1\n", encoding="utf-8")

    ctx = PipelineContext.resolve(root=tmp_path)
    assert ctx.root == tmp_path
    assert ctx.db_path == tmp_path / "data" / "articles.db"
    assert ctx.config_hash is not None
