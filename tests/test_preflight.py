"""Tests for :mod:`forensics.preflight`."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from forensics import preflight
from forensics.preflight import (
    PreflightCheck,
    PreflightReport,
    check_disk_space,
    check_no_placeholder_authors,
    check_python_version,
    run_all_preflight_checks,
)

_PLACEHOLDER_TOML = """
[[authors]]
name = "Placeholder Target"
slug = "placeholder-target"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/placeholder-target/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[scraping]
[analysis]
[report]
"""


def _placeholder_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from forensics.config import get_settings

    path = tmp_path / "config.toml"
    path.write_text(_PLACEHOLDER_TOML.strip() + "\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(path))
    get_settings.cache_clear()
    return path


def _stub_passing_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        preflight,
        "check_spacy_model",
        lambda *a, **k: PreflightCheck("spaCy model", "pass", "stub"),
    )
    monkeypatch.setattr(
        preflight,
        "check_sentence_transformer",
        lambda *a, **k: PreflightCheck("Embedding model", "pass", "stub"),
    )
    monkeypatch.setattr(
        preflight,
        "check_quarto",
        lambda: PreflightCheck("Quarto", "pass", "stub"),
    )
    monkeypatch.setattr(
        preflight,
        "check_ollama",
        lambda _s: PreflightCheck("Ollama", "pass", "stub"),
    )


def test_preflight_all_pass(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_passing_checks(monkeypatch)
    report = run_all_preflight_checks(settings)
    assert isinstance(report, PreflightReport)
    assert report.ok
    assert not report.has_failures
    names = {c.name for c in report.checks}
    assert {"Python version", "spaCy model", "Disk space", "Author config"} <= names


def test_preflight_missing_spacy(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def _raise(name: str, *args, **kwargs):
        if name == "spacy":
            raise ImportError("spacy not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise)

    result = preflight.check_spacy_model()
    assert result.status == "fail"
    assert "spacy" in result.message.lower()


def test_preflight_placeholder_authors_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from forensics.config import get_settings

    _placeholder_config(tmp_path, monkeypatch)
    try:
        settings = get_settings()
        result = check_no_placeholder_authors(settings)
        assert result.status == "fail"
        assert "placeholder" in result.message.lower()
    finally:
        get_settings.cache_clear()


def test_preflight_disk_space_low(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil as _shutil

    fake_usage = SimpleNamespace(total=0, used=0, free=1 * (1024**3))  # 1 GB
    monkeypatch.setattr(_shutil, "disk_usage", lambda _p: fake_usage)

    result = check_disk_space(tmp_path, minimum_gb=5.0)
    assert result.status == "fail"
    assert "1.0 GB free" in result.message


def test_preflight_config_parse_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from forensics.config import get_settings

    bad = tmp_path / "config.toml"
    bad.write_text("this is not valid = = toml [[[\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(bad))
    get_settings.cache_clear()
    try:
        result = preflight.check_config_parses()
        assert result.status == "fail"
        assert "config.toml" in result.message.lower()
    finally:
        get_settings.cache_clear()


def test_preflight_python_version_pass() -> None:
    result = check_python_version(minimum=(3, 0))
    assert result.status == "pass"


def test_preflight_python_version_fail() -> None:
    result = check_python_version(minimum=(99, 0))
    assert result.status == "fail"


def test_preflight_report_helpers() -> None:
    checks = (
        PreflightCheck("a", "pass", ""),
        PreflightCheck("b", "warn", ""),
        PreflightCheck("c", "fail", ""),
    )
    report = PreflightReport(checks=checks)
    assert report.has_failures
    assert report.has_warnings
    assert not report.ok
    assert [c.name for c in report.failures()] == ["c"]
    assert [c.name for c in report.warnings()] == ["b"]


def test_preflight_strict_promotes_warnings(
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_passing_checks(monkeypatch)
    monkeypatch.setattr(
        preflight,
        "check_quarto",
        lambda: PreflightCheck("Quarto", "warn", "missing"),
    )
    report = run_all_preflight_checks(settings, strict=True)
    assert any(c.status == "fail" and c.name == "Quarto" for c in report.checks)
