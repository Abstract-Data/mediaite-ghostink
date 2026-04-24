"""Analysis outputs: changepoints, drift, hypothesis tests."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ChangePoint(BaseModel):
    feature_name: str
    author_id: str
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    method: Literal["pelt", "bocpd", "chow", "cusum"]
    effect_size_cohens_d: float
    direction: Literal["increase", "decrease"]


class ConvergenceWindow(BaseModel):
    start_date: date
    end_date: date
    features_converging: list[str]
    families_converging: list[str] = Field(default_factory=list)
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


class AnalysisResult(BaseModel):
    author_id: str
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    run_timestamp: datetime
    config_hash: str
    change_points: list[ChangePoint] = Field(default_factory=list)
    convergence_windows: list[ConvergenceWindow] = Field(default_factory=list)
    drift_scores: DriftScores | None = None
    hypothesis_tests: list[HypothesisTest] = Field(default_factory=list)
