"""Unit tests for ``forensics preflight --output json`` (P2-OPS-001)."""

from __future__ import annotations

import json
import re

import pytest
from typer.testing import CliRunner

from forensics.cli import _preflight_json_envelope, app
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
    result = runner.invoke(app, ["preflight", "--output", "json"])
    assert result.exit_code == exit_code, result.output
    body = json.loads(result.output.strip())
    assert body["status"] == expected_status
    assert body["strict"] is False
    assert body["has_failures"] == (expected_status == "fail")
    assert body["has_warnings"] == (expected_status == "warn")
    assert "[PASS]" not in result.output
    assert "Some required checks failed" not in result.output


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
    expected = json.dumps(
        _preflight_json_envelope(report, strict=False),
        sort_keys=True,
    )
    result = runner.invoke(app, ["preflight", "--output", "json"])
    assert result.exit_code == 0
    assert result.output.strip() == expected


def test_preflight_help_lists_output_option() -> None:
    result = runner.invoke(app, ["preflight", "--help"])
    assert result.exit_code == 0
    assert "--output" in _plain_help(result.output)
