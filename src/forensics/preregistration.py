"""Pre-registration locking — freeze analysis thresholds before looking at data.

The lock file captures the state of every analysis threshold that affects
downstream significance decisions, together with a SHA256 content hash for
tamper detection. The analysis pipeline (and operators) can later verify
that thresholds have not silently drifted between lock and analysis time.

This is a methodological guardrail: a locked pre-registration converts an
otherwise exploratory run into a confirmatory one. A missing lock is not a
hard failure — it is simply exploratory mode — but a *mismatched* lock is
reported as a violation so humans can decide how to proceed.
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
    """Outcome of ``verify_preregistration``.

    ``status`` is one of:

    - ``ok`` — a lock file exists and the current thresholds match it.
    - ``missing`` — no lock file was found at the expected path.
    - ``mismatch`` — a lock file exists but one or more thresholds differ
      from the locked snapshot. ``diffs`` lists human-readable descriptions
      of each drifted field.
    """

    status: VerificationStatus
    message: str
    lock_path: Path
    diffs: list[str] = field(default_factory=list)


def _default_lock_path() -> Path:
    return get_project_root() / "data" / "preregistration" / "preregistration_lock.json"


def _snapshot_thresholds(settings: ForensicsSettings) -> dict[str, Any]:
    """Return the canonical dict of locked analysis thresholds."""
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
        "changepoint_methods": list(analysis.changepoint_methods),
        "rolling_windows": list(analysis.rolling_windows),
        "convergence_window_days": analysis.convergence_window_days,
        "convergence_min_feature_ratio": analysis.convergence_min_feature_ratio,
        "convergence_perplexity_drop_ratio": analysis.convergence_perplexity_drop_ratio,
        "convergence_burstiness_drop_ratio": analysis.convergence_burstiness_drop_ratio,
        "pelt_penalty": analysis.pelt_penalty,
        "pelt_cost_model": analysis.pelt_cost_model,
        "bocpd_hazard_rate": analysis.bocpd_hazard_rate,
        # Phase 15 Unit 1 — ``bocpd_threshold`` removed; the detection rule is
        # now parameterised by ``bocpd_detection_mode`` + map_reset knobs.
        "bocpd_detection_mode": analysis.bocpd_detection_mode,
        "bocpd_map_drop_ratio": analysis.bocpd_map_drop_ratio,
        "bocpd_min_run_length": analysis.bocpd_min_run_length,
        "bocpd_student_t": analysis.bocpd_student_t,
        "convergence_cp_source": analysis.convergence_cp_source,
        "convergence_drift_only_pb_threshold": analysis.convergence_drift_only_pb_threshold,
        "fdr_grouping": analysis.fdr_grouping,
        "pipeline_b_mode": analysis.pipeline_b_mode,
        "section_residualize_features": analysis.section_residualize_features,
    }


def _canonical_hash(analysis: dict[str, Any]) -> str:
    """SHA256 of the sorted, canonical JSON form of ``analysis``."""
    canonical = json.dumps(analysis, sort_keys=True, separators=(",", ":"), default=str)
    return content_hash(canonical)


def lock_preregistration(
    settings: ForensicsSettings,
    output_path: Path | None = None,
) -> Path:
    """Snapshot current analysis thresholds into a timestamped lock file.

    The payload contains:

    - ``locked_at`` — ISO-8601 UTC timestamp.
    - ``analysis`` — map of every threshold that influences significance decisions.
    - ``content_hash`` — SHA256 of the canonical JSON form of ``analysis``
      for tamper detection.
    """
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
    """Compare current thresholds against a previously written lock file.

    Returns a :class:`VerificationResult` describing whether the lock is
    present and whether it still matches. Never raises for a missing lock
    — that is reported as ``status="missing"`` so callers can distinguish
    exploratory mode from a true violation.
    """
    resolved = lock_path if lock_path is not None else _default_lock_path()
    if not resolved.is_file():
        msg = (
            "No pre-registration lock found at "
            f"{resolved}; analysis is exploratory, not confirmatory."
        )
        logger.info("preregistration: %s", msg)
        return VerificationResult(status="missing", message=msg, lock_path=resolved)

    raw = json.loads(resolved.read_text(encoding="utf-8"))

    # Operator-facing template state: the lock file exists but ``locked_at``
    # is null and ``analysis`` is absent. Treat it as "missing" (exploratory)
    # rather than "mismatch" so committing the template alone does not
    # trip a false-violation warning. Operators must lift ``locked_at`` (and
    # the ``analysis`` snapshot) before the file becomes a confirmatory lock.
    if raw.get("locked_at") is None and not raw.get("analysis"):
        msg = (
            "Pre-registration lock at "
            f"{resolved} is an unfilled template (locked_at=null, analysis "
            "absent); analysis is exploratory, not confirmatory. Run "
            "`uv run forensics lock-preregistration` to convert it."
        )
        logger.info("preregistration: %s", msg)
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
        # Rare: payload was edited in a way that keeps field equality but
        # changes canonical hash (e.g. reordering). Still a tamper signal.
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
