"""Pre-registration locking tests (Phase 12 §5a)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
        "confirmatory_split_date",
        "confirmatory_features",
        "confirmatory_test_prefixes",
        "multiple_comparison_scope",
        "significance_threshold",
        "effect_size_threshold",
        "multiple_comparison_method",
        "bootstrap_iterations",
        "min_articles_for_period",
        "embedding_model_revision",
        "enable_ks_test",
        "changepoint_methods",
        "rolling_windows",
        "convergence_window_days",
        "convergence_min_feature_ratio",
        "convergence_perplexity_drop_ratio",
        "convergence_burstiness_drop_ratio",
        "pelt_penalty",
        "pelt_cost_model",
        "bocpd_hazard_rate",
        "bocpd_hazard_auto",
        "bocpd_expected_changes_per_author",
        "bocpd_detection_mode",
        "bocpd_map_drop_ratio",
        "bocpd_min_run_length",
        "bocpd_student_t",
        "convergence_cp_source",
        "fdr_grouping",
        "enable_cross_author_correction",
        "hypothesis_min_segment_n",
        "pipeline_b_mode",
        "section_residualize_features",
    }
    assert expected_keys.issubset(analysis.keys())
    assert analysis["significance_threshold"] == settings.analysis.significance_threshold
    assert analysis["effect_size_threshold"] == settings.analysis.effect_size_threshold
    assert analysis["confirmatory_split_date"] == "2022-11-01"
    assert analysis["multiple_comparison_scope"] == "global_across_authors"


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


def test_unfilled_template_returns_missing(forensics_config_path: Path, tmp_path: Path) -> None:
    """Template with ``locked_at=null`` and no ``analysis`` → ``missing`` (not ``mismatch``)."""
    settings = get_settings()
    out = tmp_path / "preregistration_lock.json"
    template = {
        "preregistration_id": "phase15-rollout-2026-04-24",
        "locked_at": None,
        "locked_by": None,
        "config_hash": None,
        "amended_from": "data/preregistration/amendment_phase15.md",
        "amendments": ["data/preregistration/amendment_phase15.md"],
        "hypotheses": ["<author> shows family-level convergence"],
        "expected_directions": {"ai_marker_frequency": "increase"},
        "notes": "Operator MUST fill in this file.",
    }
    out.write_text(json.dumps(template, indent=2), encoding="utf-8")

    result = verify_preregistration(settings, lock_path=out)

    assert result.status == "missing"
    assert result.diffs == []
    assert "template" in result.message.lower()


def test_committed_template_lock_does_not_violate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repo ``data/preregistration`` template must not verify as ``mismatch`` vs ``config.toml``."""
    repo_root = Path(__file__).resolve().parents[1]
    cfg = repo_root / "config.toml"
    if not cfg.is_file():
        pytest.skip("repo config.toml not present")
    repo_lock = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "preregistration"
        / "preregistration_lock.json"
    )
    if not repo_lock.is_file():
        pytest.skip("template lock not present in this checkout")

    try:
        monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
        get_settings.cache_clear()
        settings = get_settings()
        result = verify_preregistration(settings, lock_path=repo_lock)

        # ``ok`` is acceptable too (operator may have filled it locally), but
        # a freshly-committed template must read as ``missing``, never ``mismatch``.
        assert result.status in {"missing", "ok"}, (
            f"committed template should not read as mismatch: {result.message}"
        )
    finally:
        monkeypatch.delenv("FORENSICS_CONFIG_FILE", raising=False)
        get_settings.cache_clear()


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


def test_run_analyze_blocks_missing_preregistration(
    forensics_config_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``run_analyze`` hard-fails when no lock exists and exploratory is not set."""
    import importlib

    analyze_mod = importlib.import_module("forensics.cli.analyze")
    from forensics.storage.repository import init_db

    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    init_db(data / "articles.db")

    calls: list[object] = []

    def fake_verify(settings_arg: object) -> VerificationResult:
        calls.append(settings_arg)
        return VerificationResult(
            status="missing",
            message="no lock",
            lock_path=tmp_path / "preregistration" / "preregistration_lock.json",
        )

    monkeypatch.setattr(analyze_mod, "verify_preregistration", fake_verify)
    monkeypatch.setattr(analyze_mod, "get_project_root", lambda: tmp_path)

    with pytest.raises(analyze_mod.typer.Exit):
        analyze_mod.run_analyze()

    assert len(calls) == 1
    assert calls[0] is get_settings()

    meta_path = tmp_path / "data" / "analysis" / "run_metadata.json"
    assert meta_path.is_file()
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    assert raw.get("preregistration_status") == "missing"
    assert raw.get("exploratory") is False


def test_run_analyze_records_exploratory_override(
    forensics_config_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--exploratory`` records the override and continues into selected stages."""
    import importlib

    analyze_mod = importlib.import_module("forensics.cli.analyze")
    from forensics.storage.repository import init_db

    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    init_db(data / "articles.db")

    calls: list[object] = []

    def fake_verify(settings_arg: object) -> VerificationResult:
        calls.append(settings_arg)
        return VerificationResult(
            status="missing",
            message="no lock",
            lock_path=tmp_path / "preregistration" / "preregistration_lock.json",
        )

    monkeypatch.setattr(analyze_mod, "verify_preregistration", fake_verify)
    monkeypatch.setattr(analyze_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(analyze_mod, "_run_timeseries_stage", lambda *a, **k: None)
    monkeypatch.setattr(analyze_mod, "_run_full_analysis_stage", lambda *a, **k: None)

    analyze_mod.run_analyze(exploratory=True)

    assert len(calls) == 1
    meta_path = tmp_path / "data" / "analysis" / "run_metadata.json"
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    assert raw.get("preregistration_status") == "missing"
    assert raw.get("exploratory") is True
