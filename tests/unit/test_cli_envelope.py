"""Unit tests for :mod:`forensics.cli._envelope` (CLI agent-readiness item 1)."""

from __future__ import annotations

import json

import pytest

from forensics.cli._envelope import SCHEMA_VERSION, emit, failure, status, success


def test_success_shape() -> None:
    got = success("foo", {"x": 1})
    assert got == {
        "ok": True,
        "type": "foo",
        "schemaVersion": SCHEMA_VERSION,
        "data": {"x": 1},
    }
    assert got["schemaVersion"] == 1


def test_success_default_data_empty() -> None:
    assert success("bar")["data"] == {}


def test_failure_shape_with_suggestion_and_extra() -> None:
    got = failure("foo", "bad", "boom", suggestion="try X", retry_after_ms=100)
    assert got == {
        "ok": False,
        "type": "foo",
        "schemaVersion": SCHEMA_VERSION,
        "error": {
            "code": "bad",
            "message": "boom",
            "suggestion": "try X",
            "retry_after_ms": 100,
        },
    }


def test_emit_writes_one_sorted_json_line(capsys: pytest.CaptureFixture[str]) -> None:
    emit(success("z", {"b": 2, "a": 1}))
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out
    assert out.endswith("\n")
    assert out.count("\n") == 1
    line = out.rstrip("\n")
    parsed = json.loads(line)
    assert parsed == success("z", {"b": 2, "a": 1})
    assert line == json.dumps(parsed, sort_keys=True)


def test_status_suppressed_in_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    status("hello", output_format="json")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_status_writes_stderr_in_text_mode(capsys: pytest.CaptureFixture[str]) -> None:
    status("hello", output_format="text")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "hello\n"


def test_forensics_output_json_preflight_single_json_stdout(
    forensics_config_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--output json`` before subcommand: one envelope on stdout; logs on stderr."""
    from typer.testing import CliRunner

    import forensics.preflight as preflight_mod
    from forensics.cli import app
    from forensics.preflight import PreflightCheck, PreflightReport

    monkeypatch.setattr(
        preflight_mod,
        "run_all_preflight_checks",
        lambda *_a, **_kw: PreflightReport(
            checks=(PreflightCheck("Only", "pass", "fine"),),
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--output", "json", "preflight"],
        color=False,
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    stdout = (result.stdout or result.output or "").strip()
    body = json.loads(stdout)
    assert body["ok"] is True
    assert body["type"] == "preflight"
    assert body["schemaVersion"] == 1
    assert body["data"]["status"] == "ok"
    stderr = result.stderr or ""
    assert not stdout.startswith("INFO ")
    if stderr:
        assert not (stderr.lstrip().startswith("{"))
