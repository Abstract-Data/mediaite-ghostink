"""P-01 — mixed per-author ``config_hash`` detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forensics.config.settings import ForensicsSettings
from forensics.utils.provenance import validate_analysis_result_config_hashes


def _write_result(path: Path, *, slug: str, config_hash: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "author_id": f"id-{slug}",
        "config_hash": config_hash,
        "change_points": [],
        "convergence_windows": [],
        "hypothesis_tests": [],
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_validate_rejects_mixed_config_hashes_across_authors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_dir = tmp_path / "analysis"
    _write_result(analysis_dir / "a_result.json", slug="a", config_hash="aaaaaaaaaaaaaaaa")
    _write_result(analysis_dir / "b_result.json", slug="b", config_hash="bbbbbbbbbbbbbbbb")

    settings = ForensicsSettings()
    monkeypatch.setattr(
        "forensics.utils.provenance.compute_analysis_config_hash",
        lambda _s: "aaaaaaaaaaaaaaaa",
    )
    ok, msg = validate_analysis_result_config_hashes(settings, analysis_dir, ["a", "b"])
    assert ok is False
    assert "mixed config_hash" in msg


def test_validate_accepts_uniform_stale_cohort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same wrong hash everywhere is 'stale', not 'mixed'."""
    analysis_dir = tmp_path / "analysis"
    _write_result(analysis_dir / "a_result.json", slug="a", config_hash="deadbeefdeadbeef")
    _write_result(analysis_dir / "b_result.json", slug="b", config_hash="deadbeefdeadbeef")

    settings = ForensicsSettings()
    monkeypatch.setattr(
        "forensics.utils.provenance.compute_analysis_config_hash",
        lambda _s: "aaaaaaaaaaaaaaaa",
    )
    ok, msg = validate_analysis_result_config_hashes(settings, analysis_dir, ["a", "b"])
    assert ok is False
    assert "mixed config_hash" not in msg
    assert "stale or mismatched" in msg


def test_validate_rejects_single_author_stale_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-04 — one slug with a mismatched ``config_hash`` must fail validation (report gate)."""
    analysis_dir = tmp_path / "analysis"
    _write_result(analysis_dir / "solo_result.json", slug="solo", config_hash="deadbeefdeadbeef")
    settings = ForensicsSettings()
    monkeypatch.setattr(
        "forensics.utils.provenance.compute_analysis_config_hash",
        lambda _s: "aaaaaaaaaaaaaaaa",
    )
    ok, msg = validate_analysis_result_config_hashes(settings, analysis_dir, ["solo"])
    assert ok is False
    assert "mixed config_hash" not in msg
    assert "stale or mismatched" in msg
