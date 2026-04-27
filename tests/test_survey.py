"""Tests for blind survey mode (Phase 12 §1 + §5c)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from forensics.models import Article, Author
from forensics.models.analysis import (
    AnalysisResult,
    ChangePoint,
    ConvergenceWindow,
    DriftScores,
    HypothesisTest,
)
from forensics.progress import NoOpPipelineObserver, PipelineRunPhase
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository
from forensics.survey import orchestrator as survey_orchestrator
from forensics.survey.orchestrator import SurveyReport, SurveyResult, run_survey
from forensics.survey.qualification import (
    QualificationCriteria,
    qualify_authors,
)
from forensics.survey.scoring import (
    ControlValidation,
    SignalStrength,
    SurveyScore,
    classify_signal,
    compute_composite_score,
    identify_natural_controls,
    validate_against_controls,
)


def _make_author(slug: str, name: str | None = None) -> Author:
    return Author(
        id=f"author-{slug}",
        name=name or slug.title().replace("-", " "),
        slug=slug,
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url=f"https://www.mediaite.com/author/{slug}/",
    )


def _make_article(
    author: Author,
    *,
    published: datetime,
    words: int = 400,
    title: str | None = None,
) -> Article:
    url = f"https://www.mediaite.com/{published.year}/{published.month:02d}/{uuid4().hex[:8]}/"
    return Article(
        id=stable_article_id(url),
        author_id=author.id,
        url=url,
        title=title or f"Post {published.date().isoformat()}",
        published_date=published,
        clean_text="body " * max(words, 1),
        word_count=words,
        content_hash=f"hash-{uuid4().hex[:8]}",
    )


def _seed(
    tmp_db: Path,
    author: Author,
    articles: list[Article],
) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(author)
        for a in articles:
            repo.upsert_article(a)


def test_qualification_filters_by_volume(tmp_db: Path) -> None:
    author = _make_author("low-volume")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 30)) for i in range(10)]
    _seed(tmp_db, author, articles)

    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(min_articles=50),
        today=date(2024, 6, 1),
    )

    assert qualified == []
    assert len(disqualified) == 1
    assert disqualified[0].author.slug == "low-volume"
    assert "too_few_articles" in (disqualified[0].disqualification_reason or "")


def test_qualification_filters_by_date_range(tmp_db: Path) -> None:
    author = _make_author("short-span")
    start = datetime(2024, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 2)) for i in range(60)]
    _seed(tmp_db, author, articles)

    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(min_articles=50, min_span_days=730),
        today=date(2024, 6, 1),
    )

    assert qualified == []
    assert disqualified and "date_range_too_short" in (
        disqualified[0].disqualification_reason or ""
    )


def test_qualification_filters_by_publishing_frequency(tmp_db: Path) -> None:
    author = _make_author("rare-publisher")
    start = datetime(2020, 1, 1, tzinfo=UTC)
    # 60 articles over ~8 years ≈ 7.5/yr, below default 12/yr threshold.
    articles = [_make_article(author, published=start + timedelta(days=i * 50)) for i in range(60)]
    _seed(tmp_db, author, articles)

    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(min_articles=50, min_span_days=365, min_articles_per_year=12.0),
        today=start.date() + timedelta(days=60 * 50 + 30),
    )

    assert qualified == []
    assert disqualified and "publishing_frequency_too_low" in (
        disqualified[0].disqualification_reason or ""
    )


def test_qualification_filters_by_recent_activity(tmp_db: Path) -> None:
    author = _make_author("stale-author")
    start = datetime(2020, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 7)) for i in range(120)]
    _seed(tmp_db, author, articles)

    # Anchor "today" far after the last article.
    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(
            min_articles=50,
            min_span_days=365,
            min_articles_per_year=5.0,
            require_recent_activity=True,
            recent_activity_days=180,
        ),
        today=date(2028, 1, 1),
    )

    assert qualified == []
    assert disqualified and "no_recent_activity" in (disqualified[0].disqualification_reason or "")


def test_qualification_all_pass(tmp_db: Path) -> None:
    author = _make_author("prolific-author")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    # 120 articles across ~3 years, 600 words each.
    articles = [
        _make_article(author, published=start + timedelta(days=i * 9), words=600)
        for i in range(120)
    ]
    _seed(tmp_db, author, articles)

    last = articles[-1].published_date.date()
    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(),
        today=last + timedelta(days=30),
    )

    assert disqualified == []
    assert len(qualified) == 1
    assert qualified[0].author.slug == "prolific-author"
    assert qualified[0].total_articles == 120
    assert qualified[0].avg_word_count == pytest.approx(600.0)


def test_qualification_no_articles_disqualified(tmp_db: Path) -> None:
    author = _make_author("ghost-author")
    _seed(tmp_db, author, [])

    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(),
        today=date(2024, 6, 1),
    )

    assert qualified == []
    assert len(disqualified) == 1
    assert disqualified[0].disqualification_reason == "no_articles"


def test_qualification_excludes_shared_bylines_by_default(tmp_db: Path) -> None:
    author = _make_author("mediaite-staff", "Mediaite Staff")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [
        _make_article(author, published=start + timedelta(days=i * 9), words=600)
        for i in range(120)
    ]
    _seed(tmp_db, author, articles)

    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(min_span_days=365),
        today=articles[-1].published_date.date() + timedelta(days=30),
    )

    assert qualified == []
    assert len(disqualified) == 1
    assert "shared_byline" in (disqualified[0].disqualification_reason or "")


def test_qualification_include_shared_bylines_escape_hatch(tmp_db: Path) -> None:
    author = _make_author("mediaite-staff", "Mediaite Staff")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [
        _make_article(author, published=start + timedelta(days=i * 9), words=600)
        for i in range(120)
    ]
    _seed(tmp_db, author, articles)

    qualified, disqualified = qualify_authors(
        tmp_db,
        QualificationCriteria(min_span_days=365, exclude_shared_bylines=False),
        today=articles[-1].published_date.date() + timedelta(days=30),
    )

    assert disqualified == []
    assert len(qualified) == 1
    assert qualified[0].author.slug == "mediaite-staff"


def _make_analysis(
    *,
    change_points: list[ChangePoint] | None = None,
    convergence_windows: list[ConvergenceWindow] | None = None,
    drift: DriftScores | None = None,
    hypothesis_tests: list[HypothesisTest] | None = None,
    run_timestamp: datetime | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        author_id="author-x",
        run_timestamp=run_timestamp or datetime(2026, 4, 25, tzinfo=UTC),
        config_hash="deadbeef",
        change_points=change_points or [],
        convergence_windows=convergence_windows or [],
        drift_scores=drift,
        hypothesis_tests=hypothesis_tests or [],
    )


def test_composite_score_no_signal_is_zero() -> None:
    analysis = _make_analysis()
    score = compute_composite_score(analysis)

    assert score.composite == 0.0
    assert score.strength == SignalStrength.NONE
    assert score.pipeline_c_score is None
    assert "no statistically significant" in score.evidence_summary.lower()


def test_composite_score_strong_signal() -> None:
    change_points = [
        ChangePoint(
            feature_name=f"feat_{i}",
            author_id="author-x",
            timestamp=datetime(2023, 6, 1, tzinfo=UTC),
            confidence=0.9,
            method="pelt",
            effect_size_cohens_d=1.2,
            direction="increase",
        )
        for i in range(18)
    ]
    windows = [
        ConvergenceWindow(
            start_date=date(2023, 6, 1),
            end_date=date(2023, 8, 30),
            features_converging=["formula_opening_score", "ai_marker_frequency", "ttr"],
            convergence_ratio=0.85,
            pipeline_a_score=0.9,
            pipeline_b_score=0.8,
            passes_via=["ratio", "ab"],
        ),
        ConvergenceWindow(
            start_date=date(2023, 9, 1),
            end_date=date(2023, 11, 30),
            features_converging=["formula_opening_score", "ai_marker_frequency"],
            convergence_ratio=0.75,
            pipeline_a_score=0.8,
            pipeline_b_score=0.7,
            passes_via=["ratio", "ab"],
        ),
    ]
    drift = DriftScores(
        author_id="author-x",
        baseline_centroid_similarity=0.5,
        ai_baseline_similarity=0.8,
        monthly_centroid_velocities=[0.1, 0.12, 0.11, 0.5, 0.6, 0.7],
        intra_period_variance_trend=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    )
    tests = [
        HypothesisTest(
            test_name="welch_t",
            feature_name="feat_0",
            author_id="author-x",
            raw_p_value=0.001,
            corrected_p_value=0.003,
            effect_size_cohens_d=1.4,
            confidence_interval_95=(0.8, 2.0),
            significant=True,
        )
    ]

    score = compute_composite_score(
        _make_analysis(
            change_points=change_points,
            convergence_windows=windows,
            drift=drift,
            hypothesis_tests=tests,
        )
    )

    assert score.strength == SignalStrength.STRONG
    assert score.composite >= 0.7
    assert score.num_convergence_windows == 2
    assert score.max_effect_size == pytest.approx(1.4)
    assert "strong signal" in score.evidence_summary.lower()


def test_composite_score_pipeline_c_included_when_available() -> None:
    windows = [
        ConvergenceWindow(
            start_date=date(2023, 6, 1),
            end_date=date(2023, 8, 30),
            features_converging=["feat_0", "feat_1"],
            convergence_ratio=0.5,
            pipeline_a_score=0.5,
            pipeline_b_score=0.5,
            pipeline_c_score=0.8,
            passes_via=["ratio"],
        )
    ]
    score = compute_composite_score(_make_analysis(convergence_windows=windows))
    assert score.pipeline_c_score == pytest.approx(0.8)


def test_signal_strength_classification_thresholds() -> None:
    assert classify_signal(0.05) == SignalStrength.NONE
    assert classify_signal(0.2) == SignalStrength.WEAK
    assert classify_signal(0.5, conv_score=0.35, max_effect=0.6) == SignalStrength.MODERATE
    assert (
        classify_signal(0.8, conv_score=0.6, max_effect=1.0, num_windows=3) == SignalStrength.STRONG
    )


def test_targeted_effect_size_escape_hatch_promotes_when_pipeline_b_silent() -> None:
    """Author with huge AI-marker effect size escapes the convergence-windows gate.

    Reproduces the false-negative class where Pipeline B sees no semantic
    drift but Pipeline A registers strong stylometric shifts on the AI-
    detection-targeted features. Without the escape hatch the composite
    stays below the moderate threshold and the author is mis-labeled NONE.
    """
    # Composite low (Pipeline B silent, no convergence) but targeted_max_effect huge.
    assert classify_signal(composite=0.06, targeted_max_effect=2.13) == SignalStrength.STRONG
    assert classify_signal(composite=0.06, targeted_max_effect=1.05) == SignalStrength.MODERATE
    assert classify_signal(composite=0.06, targeted_max_effect=0.55) == SignalStrength.WEAK
    # Below 0.5 → no promotion.
    assert classify_signal(composite=0.06, targeted_max_effect=0.40) == SignalStrength.NONE


def test_pipeline_a_targeted_path_admits_two_ai_marker_hits() -> None:
    """Two admissible AI-marker family CPs → Pipeline A = 2 × 0.35 = 0.70.

    The targeted path is now Pipeline A's only contributor (the breadth
    path was removed in Phase 15 J6 because it folded normal stylistic
    variation on continuous features into the AI score).
    """
    change_points = [
        ChangePoint(
            feature_name="formula_opening_score",
            author_id="author-x",
            timestamp=datetime(2024, 6, 1, tzinfo=UTC),
            confidence=0.95,
            method="pelt",
            effect_size_cohens_d=2.1,
            direction="increase",
        ),
        ChangePoint(
            feature_name="ai_marker_frequency",
            author_id="author-x",
            timestamp=datetime(2024, 7, 1, tzinfo=UTC),
            confidence=0.9,
            method="bocpd",
            effect_size_cohens_d=0.22,
            direction="increase",
        ),
    ]
    tests = [
        HypothesisTest(
            test_name="welch_t",
            feature_name="formula_opening_score",
            author_id="author-x",
            raw_p_value=1e-9,
            corrected_p_value=7e-9,
            effect_size_cohens_d=2.13,
            confidence_interval_95=(1.7, 2.5),
            significant=True,
        ),
    ]
    score = compute_composite_score(
        _make_analysis(change_points=change_points, hypothesis_tests=tests)
    )
    # 2 admissible AI-marker features × _AI_MARKER_PER_HIT_WEIGHT (0.35) = 0.70.
    assert score.pipeline_a_score == pytest.approx(0.7, abs=0.001)
    # Targeted-effect escape hatch promotes despite Pipeline B silence and zero
    # convergence windows — d=2.13 on AI-markers is unambiguous.
    assert score.strength in {SignalStrength.MODERATE, SignalStrength.STRONG}


def _ai_marker_cp(
    feature: str,
    ts: datetime,
    *,
    direction: str = "increase",
    d: float = 0.5,
) -> ChangePoint:
    return ChangePoint(
        feature_name=feature,
        author_id="author-x",
        timestamp=ts,
        confidence=0.95,
        method="bocpd",
        effect_size_cohens_d=d,
        direction=direction,  # type: ignore[arg-type]
    )


def test_pre_ai_era_changepoints_are_not_admissible() -> None:
    """A change-point dated before 2022-11-30 cannot evidence LLM adoption.

    Authors whose only AI-marker CPs predate ChatGPT's public launch should
    not be promoted by the targeted Pipeline A path.
    """
    change_points = [
        _ai_marker_cp("formula_opening_score", datetime(2021, 6, 1, tzinfo=UTC)),
        _ai_marker_cp("ai_marker_frequency", datetime(2022, 8, 15, tzinfo=UTC)),
    ]
    score = compute_composite_score(_make_analysis(change_points=change_points))
    # Both CPs predate the AI-era cutoff (2022-11-30) → no admissible
    # AI-marker features → targeted Pipeline A score = 0.0.
    assert score.pipeline_a_score == pytest.approx(0.0, abs=0.001)
    assert score.strength == SignalStrength.NONE


def test_decrease_direction_changepoints_are_not_admissible() -> None:
    """A *decrease* on `formula_opening_score` is the *opposite* of AI signal.

    Without the direction filter, an author who became LESS formulaic over
    time would be incorrectly counted as an AI adopter just because the
    feature changed.
    """
    change_points = [
        _ai_marker_cp(
            "formula_opening_score", datetime(2024, 6, 1, tzinfo=UTC), direction="decrease"
        ),
        _ai_marker_cp(
            "ai_marker_frequency", datetime(2024, 7, 1, tzinfo=UTC), direction="decrease"
        ),
    ]
    score = compute_composite_score(_make_analysis(change_points=change_points))
    # Both CPs are decreases on AI-marker features → no admissible features
    # → targeted Pipeline A score = 0.0.
    assert score.pipeline_a_score == pytest.approx(0.0, abs=0.001)
    assert score.strength == SignalStrength.NONE


def test_tail_of_series_changepoints_are_not_admissible() -> None:
    """CPs detected within 30 days of the analysis run lack post-CP data.

    BOCPD systematically over-detects at series boundaries because it has
    fewer than `bocpd_min_run_length` post-CP samples to confirm a sustained
    regime shift. The tail trim discards these as unstable evidence.
    """
    run_ts = datetime(2026, 4, 25, tzinfo=UTC)
    # Both CPs within the last 30 days of run_ts → trimmed.
    change_points = [
        _ai_marker_cp("formula_opening_score", datetime(2026, 4, 10, tzinfo=UTC)),
        _ai_marker_cp("ai_marker_frequency", datetime(2026, 4, 20, tzinfo=UTC)),
    ]
    score = compute_composite_score(
        _make_analysis(change_points=change_points, run_timestamp=run_ts)
    )
    # Both CPs in the tail-trim window → no admissible features → targeted
    # Pipeline A score = 0.0.
    assert score.pipeline_a_score == pytest.approx(0.0, abs=0.001)
    assert score.strength == SignalStrength.NONE


def test_drift_only_convergence_windows_are_filtered_from_score() -> None:
    """A window admitted only via `drift_only` doesn't represent real
    multi-pipeline corroboration and shouldn't inflate the convergence score.
    """
    drift_only_windows = [
        ConvergenceWindow(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 1),
            features_converging=[],
            convergence_ratio=0.0,
            pipeline_a_score=0.0,
            pipeline_b_score=0.4,
            passes_via=["drift_only"],
        ),
        ConvergenceWindow(
            start_date=date(2024, 5, 1),
            end_date=date(2024, 8, 1),
            features_converging=[],
            convergence_ratio=0.0,
            pipeline_a_score=0.0,
            pipeline_b_score=0.45,
            passes_via=["drift_only"],
        ),
    ]
    score = compute_composite_score(_make_analysis(convergence_windows=drift_only_windows))
    # Both windows filtered; convergence_score collapses to 0.
    assert score.convergence_score == 0.0
    assert score.num_convergence_windows == 2  # raw count still reflects what was detected
    assert score.strength == SignalStrength.NONE


def test_real_ab_or_ratio_convergence_windows_still_count() -> None:
    """Windows admitted via 'ab' or 'ratio' AND containing an AI-marker
    feature in features_converging are kept.
    """
    real_windows = [
        ConvergenceWindow(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 1),
            features_converging=["formula_opening_score", "ai_marker_frequency"],
            convergence_ratio=0.50,
            pipeline_a_score=0.6,
            pipeline_b_score=0.5,
            passes_via=["ab", "drift_only"],
        ),
        ConvergenceWindow(
            start_date=date(2024, 5, 1),
            end_date=date(2024, 8, 1),
            features_converging=["formula_opening_score"],
            convergence_ratio=0.33,
            pipeline_a_score=0.5,
            pipeline_b_score=0.5,
            passes_via=["ratio"],
        ),
    ]
    score = compute_composite_score(_make_analysis(convergence_windows=real_windows))
    # 2 windows × 0.2 + 0.50 × 0.8 = 0.40 + 0.40 = 0.80
    assert score.convergence_score == pytest.approx(0.8, abs=0.01)


def test_tail_of_series_convergence_windows_are_filtered() -> None:
    """Convergence windows starting within 30 days of the analysis run lack
    enough post-window data to confirm a sustained regime shift, even if
    they pass the AI-marker and post-AI-era filters.
    """
    run_ts = datetime(2026, 4, 25, tzinfo=UTC)
    tail_window = [
        ConvergenceWindow(
            start_date=date(2026, 4, 10),  # 15d before run_ts → in tail
            end_date=date(2026, 7, 10),
            features_converging=["formula_opening_score", "ai_marker_frequency"],
            convergence_ratio=0.50,
            pipeline_a_score=0.7,
            pipeline_b_score=0.5,
            passes_via=["ab", "ratio"],
        ),
    ]
    score = compute_composite_score(
        _make_analysis(convergence_windows=tail_window, run_timestamp=run_ts)
    )
    assert score.convergence_score == 0.0


def test_pre_ai_era_convergence_windows_are_filtered() -> None:
    """Convergence dated before the AI-era cutoff cannot evidence LLM
    adoption and must not contribute to convergence_score, even if it
    contains an AI-marker family feature.
    """
    pre_era_window = [
        ConvergenceWindow(
            start_date=date(2021, 6, 1),
            end_date=date(2021, 9, 1),
            features_converging=["formula_opening_score", "ai_marker_frequency"],
            convergence_ratio=0.66,
            pipeline_a_score=0.7,
            pipeline_b_score=0.5,
            passes_via=["ab", "ratio"],
        ),
    ]
    score = compute_composite_score(_make_analysis(convergence_windows=pre_era_window))
    assert score.convergence_score == 0.0


def test_convergence_windows_without_ai_marker_features_are_filtered() -> None:
    """Stylistic-only convergence (TTR + sent_length, no AI-markers) is not
    diagnostic of AI adoption and must not contribute to convergence_score.
    """
    stylistic_only_windows = [
        ConvergenceWindow(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 1),
            features_converging=["ttr", "sent_length_mean", "flesch_kincaid"],
            convergence_ratio=0.66,
            pipeline_a_score=0.7,
            pipeline_b_score=0.5,
            passes_via=["ab", "ratio"],
        ),
    ]
    score = compute_composite_score(_make_analysis(convergence_windows=stylistic_only_windows))
    # No AI-marker family feature in features_converging → window filtered.
    assert score.convergence_score == 0.0


def test_targeted_effect_requires_admissible_changepoint_corroboration() -> None:
    """A huge sig-test d on AI-markers without an admissible CP doesn't promote.

    Reproduces the false-positive class where the only AI-marker CP is in
    the tail-of-series window (and gets trimmed), but the hypothesis test
    still registers a large effect because baseline vs. post-baseline means
    differ. Without temporal corroboration, the escape hatch would still
    fire on the sig test alone.
    """
    run_ts = datetime(2026, 4, 25, tzinfo=UTC)
    # Single AI-marker CP within the tail trim window → trimmed → no
    # admissible features.
    change_points = [
        _ai_marker_cp("formula_opening_score", datetime(2026, 4, 22, tzinfo=UTC), d=2.12),
    ]
    tests = [
        HypothesisTest(
            test_name="welch_t",
            feature_name="formula_opening_score",
            author_id="author-x",
            raw_p_value=1e-9,
            corrected_p_value=7e-9,
            effect_size_cohens_d=2.12,
            confidence_interval_95=(1.7, 2.5),
            significant=True,
        ),
    ]
    score = compute_composite_score(
        _make_analysis(change_points=change_points, hypothesis_tests=tests, run_timestamp=run_ts)
    )
    # Targeted effect blocked by missing CP corroboration → no escape hatch.
    assert score.strength == SignalStrength.NONE


def test_negative_targeted_effect_does_not_promote() -> None:
    """A *negative* (decrease-direction) Cohen's d on an AI-marker test is
    *anti*-AI evidence and must not trigger the targeted-effect escape hatch.
    """
    tests = [
        HypothesisTest(
            test_name="welch_t",
            feature_name="formula_opening_score",
            author_id="author-x",
            raw_p_value=1e-9,
            corrected_p_value=7e-9,
            effect_size_cohens_d=-2.13,  # negative — getting LESS formulaic
            confidence_interval_95=(-2.5, -1.7),
            significant=True,
        ),
    ]
    score = compute_composite_score(_make_analysis(hypothesis_tests=tests))
    # No CPs, no convergence, only a strong but anti-direction targeted test
    # → must remain NONE.
    assert score.strength == SignalStrength.NONE


def test_natural_controls_identified_from_mixed_results() -> None:
    scores: dict[str, SurveyScore] = {
        "alice": SurveyScore(
            composite=0.85,
            strength=SignalStrength.STRONG,
            pipeline_a_score=0.9,
            pipeline_b_score=0.8,
            pipeline_c_score=0.7,
            convergence_score=0.7,
            num_convergence_windows=3,
            strongest_window_ratio=0.9,
            max_effect_size=1.5,
            evidence_summary="strong",
        ),
        "bob": SurveyScore(
            composite=0.05,
            strength=SignalStrength.NONE,
            pipeline_a_score=0.05,
            pipeline_b_score=0.0,
            pipeline_c_score=None,
            convergence_score=0.0,
            num_convergence_windows=0,
            strongest_window_ratio=0.0,
            max_effect_size=0.0,
            evidence_summary="nothing",
        ),
        "carol": SurveyScore(
            composite=0.08,
            strength=SignalStrength.NONE,
            pipeline_a_score=0.1,
            pipeline_b_score=0.05,
            pipeline_c_score=None,
            convergence_score=0.0,
            num_convergence_windows=0,
            strongest_window_ratio=0.0,
            max_effect_size=0.0,
            evidence_summary="nothing",
        ),
    }
    controls = identify_natural_controls(scores)
    assert controls == ["bob", "carol"]

    validation = validate_against_controls(scores, controls)
    assert isinstance(validation, ControlValidation)
    assert validation.num_controls == 2
    assert validation.mean_composite == pytest.approx((0.05 + 0.08) / 2, rel=1e-4)
    assert validation.max_composite == pytest.approx(0.08)


def _seed_qualified_corpus(tmp_db: Path, slugs: list[str]) -> None:
    start = datetime(2021, 1, 1, tzinfo=UTC)
    for slug in slugs:
        author = _make_author(slug)
        articles = [
            _make_article(author, published=start + timedelta(days=i * 8), words=500)
            for i in range(120)
        ]
        with Repository(tmp_db) as repo:
            repo.upsert_author(author)
            for a in articles:
                repo.upsert_article(a)


def _patch_orchestrator_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dispatch_result: int = 0,
) -> dict[str, list[str]]:
    """Replace scrape/extract/analysis hooks with in-memory stubs."""
    # ProcessPool workers do not inherit monkeypatches — force sequential survey
    # dispatch so stubs run in-process (checkpoint + observer tests).
    monkeypatch.setenv("SURVEY_AUTHOR_WORKERS", "1")
    calls: dict[str, list] = {
        "scrape": [],
        "extract": [],
        "analyze": [],
        "dispatch_kwargs": [],
    }

    async def fake_dispatch_scrape(**kwargs) -> int:
        calls["scrape"].append("invoked")
        calls["dispatch_kwargs"].append(
            {k: kwargs[k] for k in ("post_year_min", "post_year_max", "all_authors") if k in kwargs}
        )
        return dispatch_result

    def fake_extract(db_path, settings, *, author_slug=None, **kwargs) -> int:
        calls["extract"].append(author_slug or "")
        return 1

    def fake_run_full_analysis(paths, config, *, author_slug=None, **kwargs):
        calls["analyze"].append(author_slug or "")
        result = AnalysisResult(
            author_id=f"author-{author_slug}",
            run_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            config_hash="abc",
            change_points=[],
            convergence_windows=[],
            drift_scores=None,
            hypothesis_tests=[],
        )
        return {author_slug: result}

    # The orchestrator imports dispatch_scrape lazily inside run_survey,
    # so patch the module it pulls from.
    import forensics.cli.scrape as scrape_mod

    monkeypatch.setattr(scrape_mod, "dispatch_scrape", fake_dispatch_scrape)
    monkeypatch.setattr(survey_orchestrator, "extract_all_features", fake_extract)
    monkeypatch.setattr(survey_orchestrator, "run_full_analysis", fake_run_full_analysis)
    return calls


def test_survey_dry_run_no_analysis(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run enumerates qualified authors and never triggers analysis."""
    _seed_qualified_corpus(tmp_db, ["alice-byrne", "bob-choi"])
    calls = _patch_orchestrator_side_effects(monkeypatch)

    report = asyncio.run(
        run_survey(
            settings,
            project_root=tmp_path,
            db_path=tmp_db,
            dry_run=True,
            skip_scrape=True,
            criteria=QualificationCriteria(
                min_articles=50,
                min_span_days=365,
                min_articles_per_year=5.0,
                require_recent_activity=False,
            ),
        )
    )

    assert report.total_qualified == 2
    assert calls["scrape"] == []
    assert calls["extract"] == []
    assert calls["analyze"] == []
    assert report.run_dir is not None
    assert (report.run_dir / "survey_results.json").is_file()


def test_survey_orchestrator_checkpoints_after_each_author(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_qualified_corpus(tmp_db, ["alice-byrne", "bob-choi"])
    _patch_orchestrator_side_effects(monkeypatch)

    report = asyncio.run(
        run_survey(
            settings,
            project_root=tmp_path,
            db_path=tmp_db,
            skip_scrape=True,
            criteria=QualificationCriteria(
                min_articles=50,
                min_span_days=365,
                min_articles_per_year=5.0,
                require_recent_activity=False,
            ),
        )
    )

    assert report.run_dir is not None
    checkpoint = json.loads((report.run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert set(checkpoint["completed_slugs"]) == {"alice-byrne", "bob-choi"}
    assert checkpoint["run_id"] == report.run_id


def test_survey_orchestrator_resume_skips_completed(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_qualified_corpus(tmp_db, ["alice-byrne", "bob-choi"])
    calls = _patch_orchestrator_side_effects(monkeypatch)

    # Pre-seed a checkpoint that claims alice-byrne is already done.
    run_id = "prev-run-123"
    run_dir = tmp_path / "data" / "survey" / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "run_timestamp": datetime.now(UTC).isoformat(),
                "config_hash": "seed",
                "updated_at": datetime.now(UTC).isoformat(),
                "completed_slugs": ["alice-byrne"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = asyncio.run(
        run_survey(
            settings,
            project_root=tmp_path,
            db_path=tmp_db,
            resume=run_id,
            skip_scrape=True,
            criteria=QualificationCriteria(
                min_articles=50,
                min_span_days=365,
                min_articles_per_year=5.0,
                require_recent_activity=False,
            ),
        )
    )

    assert report.run_id == run_id
    assert calls["analyze"] == ["bob-choi"]
    assert calls["extract"] == ["bob-choi"]


def test_survey_forwards_post_year_bounds_to_dispatch_scrape(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Survey scrape step passes post year overrides into dispatch_scrape."""
    _seed_qualified_corpus(tmp_db, ["alice-byrne"])
    calls = _patch_orchestrator_side_effects(monkeypatch)

    asyncio.run(
        run_survey(
            settings,
            project_root=tmp_path,
            db_path=tmp_db,
            skip_scrape=False,
            post_year_min=2019,
            post_year_max=2022,
            criteria=QualificationCriteria(
                min_articles=50,
                min_span_days=365,
                min_articles_per_year=5.0,
                require_recent_activity=False,
            ),
        )
    )

    assert calls["scrape"] == ["invoked"]
    assert calls["dispatch_kwargs"] == [
        {"post_year_min": 2019, "post_year_max": 2022, "all_authors": True}
    ]


class _SurveyObserverRecorder(NoOpPipelineObserver):
    """Captures survey-level observer hooks for assertions."""

    def __init__(self) -> None:
        self.phases: list[str] = []
        self.authors: list[tuple[str, int, int]] = []
        self.finished: list[tuple[str, str | None]] = []

    def pipeline_run_phase_start(self, phase: PipelineRunPhase) -> None:
        self.phases.append(f"start:{phase.value}")

    def pipeline_run_phase_end(self, phase: PipelineRunPhase) -> None:
        self.phases.append(f"end:{phase.value}")

    def survey_author_started(self, slug: str, index: int, total: int) -> None:
        self.authors.append((slug, index, total))

    def survey_author_finished(self, slug: str, error: str | None = None) -> None:
        self.finished.append((slug, error))


def test_survey_observer_hooks_fire_per_author(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_survey emits survey_author_* and finalize phase events when an observer is set."""
    _seed_qualified_corpus(tmp_db, ["alice-byrne", "bob-choi"])
    _patch_orchestrator_side_effects(monkeypatch)
    obs = _SurveyObserverRecorder()

    asyncio.run(
        run_survey(
            settings,
            project_root=tmp_path,
            db_path=tmp_db,
            skip_scrape=True,
            observer=obs,
            show_rich_progress=False,
            criteria=QualificationCriteria(
                min_articles=50,
                min_span_days=365,
                min_articles_per_year=5.0,
                require_recent_activity=False,
            ),
        )
    )

    assert obs.authors == [
        ("alice-byrne", 1, 2),
        ("bob-choi", 2, 2),
    ]
    assert len(obs.finished) == 2
    assert all(sl in {"alice-byrne", "bob-choi"} and err is None for sl, err in obs.finished)
    assert "start:survey_finalize" in obs.phases
    assert "end:survey_finalize" in obs.phases


def test_survey_report_is_instance_of_SurveyReport(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke: the orchestrator returns a SurveyReport carrying SurveyResult rows."""
    _seed_qualified_corpus(tmp_db, ["alice-byrne"])
    _patch_orchestrator_side_effects(monkeypatch)

    report = asyncio.run(
        run_survey(
            settings,
            project_root=tmp_path,
            db_path=tmp_db,
            skip_scrape=True,
            criteria=QualificationCriteria(
                min_articles=50,
                min_span_days=365,
                min_articles_per_year=5.0,
                require_recent_activity=False,
            ),
        )
    )
    assert isinstance(report, SurveyReport)
    assert len(report.results) == 1
    assert isinstance(report.results[0], SurveyResult)
