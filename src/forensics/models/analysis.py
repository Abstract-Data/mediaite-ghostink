"""Analysis outputs: changepoints, drift, hypothesis tests."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


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
    convergence_ratio: float
    pipeline_a_score: float
    pipeline_b_score: float
    pipeline_c_score: float | None = None


class DriftScores(BaseModel):
    author_id: str
    baseline_centroid_similarity: float
    ai_baseline_similarity: float | None = None
    monthly_centroid_velocities: list[float]
    intra_period_variance_trend: list[float]


class HypothesisTest(BaseModel):
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
