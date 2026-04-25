"""Analysis outputs: changepoints, drift, hypothesis tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ChangePoint(BaseModel):
    feature_name: str
    author_id: str
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    method: Literal[
        "pelt",
        "bocpd",
        "pelt_section_adjusted",
        "bocpd_section_adjusted",
        "chow",
        "cusum",
    ]
    effect_size_cohens_d: float
    direction: Literal["increase", "decrease"]


class ConvergenceWindow(BaseModel):
    start_date: date
    end_date: date
    features_converging: list[str]
    families_converging: list[str] = Field(default_factory=list)
    # Phase 16 D5 — per-family count of distinct features with BH-rankable
    # hypothesis-test rows for this author run (Welch/MW/KS battery).
    n_rankable_per_family: dict[str, int] = Field(default_factory=dict)
    convergence_ratio: float
    pipeline_a_score: float
    pipeline_b_score: float
    pipeline_c_score: float | None = None
    # Phase 15 Fix-G — which gate(s) admitted this window. Allowed entries:
    # ``"ratio"``, ``"ab"``, ``"drift_only"``. The list preserves insertion
    # order from ``_score_single_window`` so consumers can render
    # multi-channel admission cleanly. Default empty for backward compatibility
    # with pre-Fix-G persisted artifacts.
    passes_via: list[str] = Field(default_factory=list)


class DriftScores(BaseModel):
    author_id: str
    baseline_centroid_similarity: float
    ai_baseline_similarity: float | None = None
    monthly_centroid_velocities: list[float]
    intra_period_variance_trend: list[float]

    @property
    def velocity_acceleration_ratio(self) -> float:
        """(late-early)/early split of ``monthly_centroid_velocities`` clamped to [0, 1]."""
        # Deferred import breaks the models → analysis → models cycle
        # (``forensics.analysis.utils`` re-exports helpers that themselves
        # reference models in this module). Keeping it local to the property
        # avoids the import happening at module-load time.
        from forensics.analysis.utils import compute_velocity_acceleration

        return compute_velocity_acceleration(self.monthly_centroid_velocities)


class HypothesisTest(BaseModel):
    """Immutable hypothesis-test record.

    ``apply_correction`` and ``filter_by_effect_size`` now return new instances
    via ``model_copy`` rather than mutating shared objects (P2-MAINT-002).

    Phase 16 D1: ``n_pre`` / ``n_post`` default to ``-1`` for legacy JSON rows
    that predate finite-sample bookkeeping; use :meth:`from_legacy` when loading
    untyped payloads for the report stage.
    """

    model_config = ConfigDict(frozen=True)

    test_name: str
    feature_name: str
    author_id: str
    raw_p_value: float
    corrected_p_value: float
    effect_size_cohens_d: float
    confidence_interval_95: tuple[float, float]
    significant: bool
    # Sample bookkeeping (confirmatory runs); -1 = unknown / legacy artifact.
    n_pre: int = Field(default=-1, ge=-1)
    n_post: int = Field(default=-1, ge=-1)
    n_nan_dropped: int = Field(default=0, ge=0)
    skipped_reason: str | None = None
    degenerate: bool = False

    @classmethod
    def from_legacy(cls, data: Any) -> Self:
        """Validate ``data`` and default missing Phase-16 sample fields for legacy JSON."""
        if isinstance(data, HypothesisTest):
            return data
        if not isinstance(data, Mapping):
            return cls.model_validate(data)
        payload = dict(data)
        payload.setdefault("n_pre", -1)
        payload.setdefault("n_post", -1)
        payload.setdefault("n_nan_dropped", 0)
        payload.setdefault("skipped_reason", None)
        payload.setdefault("degenerate", False)
        return cls.model_validate(payload)


class EraClassification(BaseModel):
    ai_marker_change_points_by_era: dict[str, int] = Field(default_factory=dict)
    dominant_era: (
        Literal[
            "pre_nov_2022",
            "nov_2022_to_mar_2023",
            "mar_2023_to_dec_2023",
            "post_dec_2023",
        ]
        | None
    ) = None
    total_ai_marker_change_points: int = 0


class AnalysisResult(BaseModel):
    author_id: str
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    run_timestamp: datetime
    config_hash: str
    change_points: list[ChangePoint] = Field(default_factory=list)
    convergence_windows: list[ConvergenceWindow] = Field(default_factory=list)
    drift_scores: DriftScores | None = None
    hypothesis_tests: list[HypothesisTest] = Field(default_factory=list)
    era_classification: EraClassification = Field(default_factory=EraClassification)


class CorpusCustody(BaseModel):
    """Chain-of-custody record persisted as ``corpus_custody.json`` (Phase 16 schema v2).

    ``corpus_hash`` fingerprints the *analyzable* corpus: rows with ``is_duplicate = 0``,
    ordered by ``content_hash`` (stable under insert / primary-key order).
    ``corpus_hash_v1`` stores the legacy id-ordered hash (including duplicates) for one
    transition cycle of audit tooling; remove after Phase 17 (see GUARDRAILS).
    """

    schema_version: int = Field(2, ge=1, le=2)
    corpus_hash: str
    corpus_hash_v1: str | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
