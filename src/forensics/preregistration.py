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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from forensics.config.settings import ForensicsSettings, get_project_root
from forensics.utils.hashing import content_hash

logger = logging.getLogger(__name__)


VerificationStatus = Literal["ok", "missing", "mismatch"]


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
        "bocpd_hazard_rate": analysis.bocpd_hazard_rate,
        "bocpd_threshold": analysis.bocpd_threshold,
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
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    analysis = _snapshot_thresholds(settings)
    payload: dict[str, Any] = {
        "locked_at": datetime.now(UTC).isoformat(),
        "analysis": analysis,
        "content_hash": _canonical_hash(analysis),
    }

    lock_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
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
    "lock_preregistration",
    "verify_preregistration",
]
