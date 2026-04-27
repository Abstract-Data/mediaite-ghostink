"""Unit tests for ``forensics --output json preflight`` (P2-OPS-001)."""

from __future__ import annotations

import json
import re

import pytest
from typer.testing import CliRunner

from forensics.cli import _preflight_json_envelope, app
from forensics.cli._envelope import success
from forensics.preflight import PreflightCheck, PreflightReport

runner = CliRunner()


def _plain_help(output: str) -> str:
    """Rich/Typer help uses ANSI sequences; strip them for substring assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", output)


def test_preflight_json_envelope_sort_keys_match_cli_encoder() -> None:
    """Top-level and per-check keys match ``json.dumps(..., sort_keys=True)`` ordering."""
    report = PreflightReport(
        checks=(
            PreflightCheck("Zeta", "pass", "detail"),
            PreflightCheck("Alpha", "warn", "heads up"),
        ),
    )
    payload = _preflight_json_envelope(report, strict=True)
    encoded = json.dumps(payload, sort_keys=True)
    parsed = json.loads(encoded)
    assert parsed["status"] == "warn"
    assert parsed["strict"] is True
    assert parsed["has_failures"] is False
    assert parsed["has_warnings"] is True
    assert list(parsed.keys()) == sorted(parsed.keys())
    for row in parsed["checks"]:
        assert list(row.keys()) == sorted(row.keys())


@pytest.mark.parametrize(
    ("checks", "expected_status", "exit_code"),
    [
        (
            (
                PreflightCheck("Config file", "pass", "ok"),
                PreflightCheck("Python version", "pass", "3.13"),
            ),
            "ok",
            0,
        ),
        (
            (PreflightCheck("Quarto", "warn", "missing"),),
            "warn",
            0,
        ),
        (
            (PreflightCheck("Disk space", "fail", "full"),),
            "fail",
            1,
        ),
    ],
)
def test_preflight_json_status_and_exit(
    forensics_config_path: object,
    monkeypatch: pytest.MonkeyPatch,
    checks: tuple[PreflightCheck, ...],
    expected_status: str,
    exit_code: int,
) -> None:
    import forensics.preflight as preflight_mod

    monkeypatch.setattr(
        preflight_mod,
        "run_all_preflight_checks",
        lambda *_a, **_kw: PreflightReport(checks=checks),
    )
    result = runner.invoke(app, ["--output", "json", "preflight"], color=False)
    assert result.exit_code == exit_code, (result.stdout or "") + (result.stderr or "")
    stdout = (result.stdout or result.output or "").strip()
    body = json.loads(stdout)
    assert body["ok"] is True
    assert body["type"] == "preflight"
    assert body["schemaVersion"] == 1
    data = body["data"]
    assert data["status"] == expected_status
    assert data["strict"] is False
    assert data["has_failures"] == (expected_status == "fail")
    assert data["has_warnings"] == (expected_status == "warn")
    assert "[PASS]" not in stdout
    assert "Some required checks failed" not in stdout


def test_preflight_json_deterministic_exact_payload(
    forensics_config_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: stdout must match canonical ``sort_keys`` serialization byte-for-byte."""
    import forensics.preflight as preflight_mod

    report = PreflightReport(checks=(PreflightCheck("Only", "pass", "fine"),))
    monkeypatch.setattr(
        preflight_mod,
        "run_all_preflight_checks",
        lambda *_a, **_kw: report,
    )
    inner = _preflight_json_envelope(report, strict=False)
    expected = json.dumps(success("preflight", inner), sort_keys=True)
    result = runner.invoke(app, ["--output", "json", "preflight"], color=False)
    assert result.exit_code == 0
    assert (result.stdout or result.output or "").strip() == expected


def test_preflight_help_root_lists_global_output_option() -> None:
    """``--output`` is a root callback option (must appear before subcommand)."""
    result = runner.invoke(app, ["--help"], color=False)
    assert result.exit_code == 0
    assert "--output" in _plain_help(result.stdout or result.output)
