"""Pre-registration locking tests (Phase 12 §5a)."""

from __future__ import annotations

import json
from pathlib import Path

from forensics.config import get_settings
from forensics.preregistration import (
    VerificationResult,
    lock_preregistration,
    verify_preregistration,
)


def test_lock_creates_file(forensics_config_path: Path, tmp_path: Path) -> None:
    """Lock writes a JSON file at the requested path (creating parents)."""
    settings = get_settings()
    out = tmp_path / "preregistration" / "preregistration_lock.json"

    path = lock_preregistration(settings, output_path=out)

    assert path == out
    assert path.is_file()
    assert path.parent.is_dir()


def test_lock_content_has_thresholds(forensics_config_path: Path, tmp_path: Path) -> None:
    """Lock payload carries every required threshold plus a SHA256 hash."""
    settings = get_settings()
    out = tmp_path / "lock.json"

    lock_preregistration(settings, output_path=out)
    raw = json.loads(out.read_text(encoding="utf-8"))

    assert "locked_at" in raw
    assert "content_hash" in raw
    assert len(raw["content_hash"]) == 64  # SHA256 hex digest
    analysis = raw["analysis"]
    expected_keys = {
        "significance_threshold",
        "effect_size_threshold",
        "multiple_comparison_method",
        "bootstrap_iterations",
        "min_articles_for_period",
        "changepoint_methods",
        "rolling_windows",
        "convergence_window_days",
        "convergence_min_feature_ratio",
        "convergence_perplexity_drop_ratio",
        "convergence_burstiness_drop_ratio",
        "pelt_penalty",
        "bocpd_hazard_rate",
        "bocpd_threshold",
    }
    assert expected_keys.issubset(analysis.keys())
    assert analysis["significance_threshold"] == settings.analysis.significance_threshold
    assert analysis["effect_size_threshold"] == settings.analysis.effect_size_threshold


def test_verify_matches_when_unchanged(forensics_config_path: Path, tmp_path: Path) -> None:
    """Lock then immediately verify → ``ok``."""
    settings = get_settings()
    out = tmp_path / "lock.json"

    lock_preregistration(settings, output_path=out)
    result = verify_preregistration(settings, lock_path=out)

    assert isinstance(result, VerificationResult)
    assert result.status == "ok"
    assert result.diffs == []
    assert "intact" in result.message.lower()


def test_verify_fails_when_significance_changed(
    forensics_config_path: Path, tmp_path: Path
) -> None:
    """Mutating the significance threshold after locking → ``mismatch`` with diff."""
    settings = get_settings()
    out = tmp_path / "lock.json"

    lock_preregistration(settings, output_path=out)
    # Mutate in-place — pydantic v2 models permit attribute assignment by default.
    settings.analysis.significance_threshold = 0.01

    result = verify_preregistration(settings, lock_path=out)

    assert result.status == "mismatch"
    assert any("significance_threshold" in d for d in result.diffs)
    assert "VIOLATED" in result.message


def test_verify_fails_when_methods_changed(forensics_config_path: Path, tmp_path: Path) -> None:
    """Changing ``changepoint_methods`` after locking → ``mismatch``."""
    settings = get_settings()
    out = tmp_path / "lock.json"

    lock_preregistration(settings, output_path=out)
    settings.analysis.changepoint_methods = ["pelt"]

    result = verify_preregistration(settings, lock_path=out)

    assert result.status == "mismatch"
    assert any("changepoint_methods" in d for d in result.diffs)


def test_no_lock_file_returns_missing(forensics_config_path: Path, tmp_path: Path) -> None:
    """Verifying without a lock file returns ``missing`` (exploratory mode)."""
    settings = get_settings()
    out = tmp_path / "does-not-exist.json"

    result = verify_preregistration(settings, lock_path=out)

    assert result.status == "missing"
    assert result.diffs == []
    assert result.lock_path == out


def test_lock_is_idempotent(forensics_config_path: Path, tmp_path: Path) -> None:
    """Second lock overwrites the first and verification still succeeds."""
    settings = get_settings()
    out = tmp_path / "lock.json"

    lock_preregistration(settings, output_path=out)
    first_hash = json.loads(out.read_text(encoding="utf-8"))["content_hash"]

    lock_preregistration(settings, output_path=out)
    second_hash = json.loads(out.read_text(encoding="utf-8"))["content_hash"]

    # Thresholds unchanged → canonical hash stable
    assert first_hash == second_hash
    assert verify_preregistration(settings, lock_path=out).status == "ok"
