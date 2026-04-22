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
