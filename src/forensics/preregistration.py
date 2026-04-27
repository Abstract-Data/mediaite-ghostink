"""Pre-registration lock: snapshot analysis thresholds + SHA256 for drift checks.

Missing lock → exploratory; mismatch → :func:`verify_preregistration` reports
``mismatch`` so operators can reconcile thresholds vs. the lock file.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from forensics.config.settings import ForensicsSettings, get_project_root
from forensics.storage.json_io import write_text_atomic
from forensics.utils.hashing import content_hash

logger = logging.getLogger(__name__)


VerificationStatus = Literal["ok", "missing", "mismatch"]

PREREGISTERED_SPLIT_DATE = date(2022, 11, 1)
PREREGISTERED_FEATURES: tuple[str, ...] = (
    "ai_marker_frequency",
    "ttr",
    "mattr",
    "sent_length_mean",
    "paragraph_length_variance",
    "hedging_frequency",
)
PREREGISTERED_TEST_PREFIXES: tuple[str, ...] = ("welch_t", "mann_whitney")


@dataclass(frozen=True)
class VerificationResult:
    """``verify_preregistration`` outcome: ``ok`` | ``missing`` | ``mismatch`` (+ ``diffs``)."""

    status: VerificationStatus
    message: str
    lock_path: Path
    diffs: list[str] = field(default_factory=list)


def _default_lock_path() -> Path:
    return get_project_root() / "data" / "preregistration" / "preregistration_lock.json"


def _snapshot_thresholds(settings: ForensicsSettings) -> dict[str, Any]:
    """Locked analysis-threshold map (preregistered fields)."""
    analysis = settings.analysis
    return {
        "confirmatory_split_date": PREREGISTERED_SPLIT_DATE.isoformat(),
        "confirmatory_features": list(PREREGISTERED_FEATURES),
        "confirmatory_test_prefixes": list(PREREGISTERED_TEST_PREFIXES),
        "multiple_comparison_scope": "global_across_authors",
        "significance_threshold": analysis.significance_threshold,
        "effect_size_threshold": analysis.effect_size_threshold,
        "multiple_comparison_method": analysis.multiple_comparison_method,
        "bootstrap_iterations": analysis.bootstrap_iterations,
        "min_articles_for_period": analysis.min_articles_for_period,
        "embedding_model_revision": analysis.embedding_model_revision,
        "enable_ks_test": analysis.enable_ks_test,
        "changepoint_methods": list(analysis.changepoint_methods),
        "rolling_windows": list(analysis.rolling_windows),
        "convergence_window_days": analysis.convergence_window_days,
        "convergence_min_feature_ratio": analysis.convergence_min_feature_ratio,
        "convergence_perplexity_drop_ratio": analysis.convergence_perplexity_drop_ratio,
        "convergence_burstiness_drop_ratio": analysis.convergence_burstiness_drop_ratio,
        "pelt_penalty": analysis.pelt_penalty,
        "pelt_cost_model": analysis.pelt_cost_model,
        "bocpd_hazard_rate": analysis.bocpd_hazard_rate,
        # BOCPD: ``bocpd_threshold`` removed (Phase 15 U1); mode + map_reset knobs apply.
        "bocpd_detection_mode": analysis.bocpd_detection_mode,
        "bocpd_map_drop_ratio": analysis.bocpd_map_drop_ratio,
        "bocpd_min_run_length": analysis.bocpd_min_run_length,
        "bocpd_student_t": analysis.bocpd_student_t,
        "convergence_cp_source": analysis.convergence_cp_source,
        "convergence_drift_only_pb_threshold": analysis.convergence_drift_only_pb_threshold,
        "fdr_grouping": analysis.fdr_grouping,
        "enable_cross_author_correction": analysis.enable_cross_author_correction,
        "hypothesis_min_segment_n": analysis.hypothesis_min_segment_n,
        "bocpd_hazard_auto": analysis.bocpd_hazard_auto,
        "bocpd_expected_changes_per_author": analysis.bocpd_expected_changes_per_author,
        "pipeline_b_mode": analysis.pipeline_b_mode,
        "section_residualize_features": analysis.section_residualize_features,
    }


def _canonical_hash(analysis: dict[str, Any]) -> str:
    """SHA256 of sorted canonical JSON for ``analysis``."""
    canonical = json.dumps(analysis, sort_keys=True, separators=(",", ":"), default=str)
    return content_hash(canonical)


def lock_preregistration(
    settings: ForensicsSettings,
    output_path: Path | None = None,
) -> Path:
    """Write ``locked_at``, ``analysis`` thresholds, and ``content_hash`` to ``lock_path``."""
    lock_path = output_path if output_path is not None else _default_lock_path()

    analysis = _snapshot_thresholds(settings)
    payload: dict[str, Any] = {
        "locked_at": datetime.now(UTC).isoformat(),
        "analysis": analysis,
        "content_hash": _canonical_hash(analysis),
    }

    write_text_atomic(
        lock_path,
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
    )
    logger.info("preregistration: locked thresholds to %s", lock_path)
    return lock_path


def verify_preregistration(
    settings: ForensicsSettings,
    lock_path: Path | None = None,
) -> VerificationResult:
    """Compare live settings to ``lock_path``; missing file → ``missing`` (no raise)."""
    resolved = lock_path if lock_path is not None else _default_lock_path()
    if not resolved.is_file():
        msg = (
            "No pre-registration lock found at "
            f"{resolved}; analysis is exploratory, not confirmatory."
        )
        logger.warning("preregistration: %s (L-06)", msg)
        return VerificationResult(status="missing", message=msg, lock_path=resolved)

    raw = json.loads(resolved.read_text(encoding="utf-8"))

    # Unfilled template (``locked_at`` null, no ``analysis``) → ``missing``, not ``mismatch``.
    if raw.get("locked_at") is None and not raw.get("analysis"):
        msg = (
            "Pre-registration lock at "
            f"{resolved} is an unfilled template (locked_at=null, analysis "
            "absent); analysis is exploratory, not confirmatory. Run "
            "`uv run forensics lock-preregistration` to convert it."
        )
        logger.warning("preregistration: %s (L-06)", msg)
        return VerificationResult(status="missing", message=msg, lock_path=resolved)

    locked_analysis: dict[str, Any] = raw.get("analysis", {})
    locked_hash: str | None = raw.get("content_hash")

    current = _snapshot_thresholds(settings)
    current_hash = _canonical_hash(current)

    diffs: list[str] = []
    all_keys = sorted(set(locked_analysis) | set(current))
    for key in all_keys:
        if locked_analysis.get(key) != current.get(key):
            diffs.append(
                f"{key}: locked={locked_analysis.get(key)!r}, current={current.get(key)!r}"
            )

    if locked_hash is not None and locked_hash != current_hash and not diffs:
        # Field-equal payload but hash drift (e.g. reorder) — still report.
        diffs.append(f"content_hash: locked={locked_hash}, current={current_hash}")

    if diffs:
        msg = "Pre-registration VIOLATED — thresholds changed since lock: " + "; ".join(diffs)
        logger.warning("preregistration: %s", msg)
        return VerificationResult(status="mismatch", message=msg, lock_path=resolved, diffs=diffs)

    msg = f"Pre-registration intact (locked at {raw.get('locked_at', 'unknown')})"
    logger.info("preregistration: %s", msg)
    return VerificationResult(status="ok", message=msg, lock_path=resolved)


__all__ = [
    "VerificationResult",
    "VerificationStatus",
    "PREREGISTERED_FEATURES",
    "PREREGISTERED_SPLIT_DATE",
    "PREREGISTERED_TEST_PREFIXES",
    "lock_preregistration",
    "verify_preregistration",
]
