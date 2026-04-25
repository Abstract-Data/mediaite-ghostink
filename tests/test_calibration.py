"""Tests for the calibration suite (Phase 12 §4 + §10)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from forensics.calibration import runner as runner_mod
from forensics.calibration.runner import (
    CalibrationTrial,
    compute_metrics,
    run_calibration,
)
from forensics.calibration.synthetic import (
    SyntheticCorpus,
    build_negative_control,
    build_spliced_corpus,
)
from forensics.models import Article, Author
from forensics.models.analysis import AnalysisResult, ChangePoint
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository
from forensics.survey.scoring import SignalStrength

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_author(slug: str = "test-author") -> Author:
    return Author(
        id=f"author-{slug}",
        name=slug.title().replace("-", " "),
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
    text: str = "original body text " * 20,
) -> Article:
    url = f"https://www.mediaite.com/{published.year}/{published.month:02d}/{uuid4().hex[:8]}/"
    return Article(
        id=stable_article_id(url),
        author_id=author.id,
        url=url,
        title=f"Post {published.date().isoformat()}",
        published_date=published,
        clean_text=text,
        word_count=len(text.split()),
        content_hash=f"hash-{uuid4().hex[:8]}",
    )


def _make_ai_article(published: datetime, text: str) -> Article:
    url = f"https://example.com/ai/{uuid4().hex[:8]}"
    return Article(
        id=f"ai-{uuid4().hex[:8]}",
        author_id="ai-baseline",
        url=url,
        title="AI Generated",
        published_date=published,
        clean_text=text,
        word_count=len(text.split()),
        content_hash="",
    )


def _make_analysis(
    *,
    cp_dates: list[date] | None = None,
    n_windows: int = 0,
) -> AnalysisResult:
    from forensics.models.analysis import ConvergenceWindow

    cps = [
        ChangePoint(
            feature_name=f"feat_{i}",
            author_id="author-x",
            timestamp=datetime(d.year, d.month, d.day, tzinfo=UTC),
            confidence=0.9,
            method="pelt",
            effect_size_cohens_d=1.0,
            direction="increase",
        )
        for i, d in enumerate(cp_dates or [])
    ]
    windows = [
        ConvergenceWindow(
            start_date=date(2023, 6, 1),
            end_date=date(2023, 9, 1),
            features_converging=[f"feat_{i}" for i in range(12)],
            convergence_ratio=0.8,
            pipeline_a_score=0.9,
            pipeline_b_score=0.8,
        )
        for _ in range(n_windows)
    ]
    return AnalysisResult(
        author_id="author-x",
        run_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        config_hash="deadbeef",
        change_points=cps,
        convergence_windows=windows,
    )


# ---------------------------------------------------------------------------
# synthetic corpus builder
# ---------------------------------------------------------------------------


def test_build_spliced_corpus_correct_split() -> None:
    author = _make_author("split-test")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 10)) for i in range(20)]
    ai_articles = [
        _make_ai_article(start + timedelta(days=i * 10), text=f"ai body {i} " * 30)
        for i in range(20)
    ]
    splice = (start + timedelta(days=9 * 10)).date()

    corpus = build_spliced_corpus(author.slug, articles, splice, ai_articles)

    assert isinstance(corpus, SyntheticCorpus)
    assert corpus.splice_date == splice
    assert len(corpus.combined_articles) == len(articles)
    pre = [a for a in corpus.combined_articles if a.published_date.date() <= splice]
    post = [a for a in corpus.combined_articles if a.published_date.date() > splice]
    # Half the timeline authored-only; second half contains synthetic replacements.
    assert all("synthetic" not in (a.metadata or {}) for a in pre)
    assert all(a.metadata.get("synthetic") is True for a in post)
    assert len(post) == len([a for a in articles if a.published_date.date() > splice])


def test_build_spliced_corpus_preserves_dates() -> None:
    author = _make_author("date-preserve")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 5)) for i in range(10)]
    ai_articles = [
        _make_ai_article(
            datetime(2099, 1, 1, tzinfo=UTC),  # intentionally bogus date
            text="ai text " * 40,
        )
        for _ in range(10)
    ]
    splice = (start + timedelta(days=4 * 5)).date()

    corpus = build_spliced_corpus(author.slug, articles, splice, ai_articles)

    # Every combined article preserves its original published_date.
    original_dates = sorted(a.published_date for a in articles)
    combined_dates = sorted(a.published_date for a in corpus.combined_articles)
    assert combined_dates == original_dates


def test_build_negative_control_unmodified() -> None:
    author = _make_author("nc")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 3)) for i in range(7)]

    nc = build_negative_control(author.slug, articles)

    assert nc.splice_date is None
    assert nc.synthetic_articles == []
    assert len(nc.combined_articles) == len(articles)
    # Identity transform preserves clean_text and id.
    for orig, copy in zip(
        sorted(articles, key=lambda a: a.published_date),
        nc.combined_articles,
        strict=True,
    ):
        assert copy.id == orig.id
        assert copy.clean_text == orig.clean_text


# ---------------------------------------------------------------------------
# metric correctness
# ---------------------------------------------------------------------------


def _trial(is_positive: bool, detected: bool, date_err: int | None = None) -> CalibrationTrial:
    return CalibrationTrial(
        author_slug="x",
        splice_date=date(2023, 1, 1) if is_positive else None,
        is_positive=is_positive,
        detected=detected,
        detection_date=date(2023, 1, 1) if detected else None,
        composite_score=0.5 if detected else 0.0,
        convergence_windows=1 if detected else 0,
        date_error_days=date_err,
    )


def test_calibration_report_metrics_correct() -> None:
    # 3 TP, 1 FN, 2 TN, 1 FP
    trials = [
        _trial(True, True, 5),
        _trial(True, True, 10),
        _trial(True, True, 15),
        _trial(True, False),
        _trial(False, False),
        _trial(False, False),
        _trial(False, True),
    ]
    m = compute_metrics(trials)
    # sensitivity = TP / (TP+FN) = 3/4
    assert m["sensitivity"] == pytest.approx(0.75)
    # specificity = TN / (TN+FP) = 2/3
    assert m["specificity"] == pytest.approx(2 / 3)
    # precision = TP / (TP+FP) = 3/4
    assert m["precision"] == pytest.approx(0.75)
    # F1 = 2*P*R / (P+R) = 0.75
    assert m["f1_score"] == pytest.approx(0.75)
    # median of [5, 10, 15] = 10
    assert m["median_date_error_days"] == pytest.approx(10.0)


def test_calibration_metrics_handle_empty_groups() -> None:
    # No positives → sensitivity undefined (return 0) but specificity well-defined.
    trials = [_trial(False, False), _trial(False, False)]
    m = compute_metrics(trials)
    assert m["sensitivity"] == 0.0
    assert m["specificity"] == 1.0
    assert m["f1_score"] == 0.0
    assert m["median_date_error_days"] is None


def test_marker_discrimination_scorer_filters_non_finite_values() -> None:
    from forensics.calibration.markers import score_marker_discrimination

    score = score_marker_discrimination(
        human_frequencies=[0.0, 0.01, float("nan")],
        ai_frequencies=[0.12, 0.18, float("inf")],
        minimum_separation=0.05,
    )

    assert score.human_mean == pytest.approx(0.005)
    assert score.ai_mean == pytest.approx(0.15)
    assert score.separation == pytest.approx(0.145)
    assert score.passes_threshold is True


# ---------------------------------------------------------------------------
# runner — perfect + blind detector (mocked analysis)
# ---------------------------------------------------------------------------


def _seed_db_with_author(db_path: Path, author: Author, articles: list[Article]) -> None:
    with Repository(db_path) as repo:
        repo.upsert_author(author)
        for a in articles:
            repo.upsert_article(a)


def _install_mock_trial_analysis(
    monkeypatch: pytest.MonkeyPatch,
    *,
    positive_analysis: AnalysisResult | None,
    negative_analysis: AnalysisResult | None,
) -> None:
    """Replace the expensive trial step with a deterministic stub."""

    async def fake_run_trial_analysis(
        corpus: SyntheticCorpus,
        author: Author,
        *,
        settings,
        project_root: Path,
        trial_root: Path,
    ) -> AnalysisResult | None:
        # No filesystem writes, no extract, no analysis — just return the
        # pre-canned analysis based on whether this is a positive or negative.
        return positive_analysis if corpus.splice_date is not None else negative_analysis

    monkeypatch.setattr(runner_mod, "_run_trial_analysis", fake_run_trial_analysis)


def _install_mock_composite(
    monkeypatch: pytest.MonkeyPatch,
    *,
    positive_score: float,
    positive_strength: SignalStrength,
    negative_score: float,
    negative_strength: SignalStrength,
) -> None:
    """Replace ``compute_composite_score`` to flip the detector on/off."""

    from forensics.survey.scoring import SurveyScore

    def fake_compute_composite_score(analysis, qualification=None):  # noqa: ARG001
        # Distinguish positive vs negative: the positive analysis has changepoints,
        # the negative one has none.
        is_positive = bool(getattr(analysis, "change_points", []))
        return SurveyScore(
            composite=positive_score if is_positive else negative_score,
            strength=positive_strength if is_positive else negative_strength,
            pipeline_a_score=0.0,
            pipeline_b_score=0.0,
            pipeline_c_score=None,
            convergence_score=0.0,
            num_convergence_windows=0,
            strongest_window_ratio=0.0,
            max_effect_size=0.0,
            evidence_summary="mock",
        )

    monkeypatch.setattr(runner_mod, "compute_composite_score", fake_compute_composite_score)


@pytest.mark.asyncio
async def test_calibration_perfect_detector(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock compute_composite_score to always flag positives and never negatives."""
    author = _make_author("perfect")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 5)) for i in range(30)]
    _seed_db_with_author(tmp_db, author, articles)

    # Positive → non-empty changepoints; negative → empty changepoints.
    positive = _make_analysis(cp_dates=[date(2022, 1, 15)], n_windows=2)
    negative = _make_analysis()

    _install_mock_trial_analysis(
        monkeypatch,
        positive_analysis=positive,
        negative_analysis=negative,
    )
    _install_mock_composite(
        monkeypatch,
        positive_score=0.9,
        positive_strength=SignalStrength.STRONG,
        negative_score=0.0,
        negative_strength=SignalStrength.NONE,
    )

    report = await run_calibration(
        settings,
        positive_trials=3,
        negative_trials=3,
        author=author.slug,
        seed=7,
        project_root=tmp_path,
        db_path=tmp_db,
    )

    assert len(report.trials) == 6
    assert report.sensitivity == pytest.approx(1.0)
    assert report.specificity == pytest.approx(1.0)
    assert report.precision == pytest.approx(1.0)
    assert report.f1_score == pytest.approx(1.0)
    assert report.report_path is not None and report.report_path.is_file()
    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["n_trials"] == 6
    assert payload["sensitivity"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_calibration_blind_detector(
    tmp_db: Path,
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock detector to never fire → sensitivity 0, specificity 1."""
    author = _make_author("blind")
    start = datetime(2021, 1, 1, tzinfo=UTC)
    articles = [_make_article(author, published=start + timedelta(days=i * 5)) for i in range(30)]
    _seed_db_with_author(tmp_db, author, articles)

    positive = _make_analysis(cp_dates=[date(2022, 3, 1)], n_windows=1)
    negative = _make_analysis()

    _install_mock_trial_analysis(
        monkeypatch,
        positive_analysis=positive,
        negative_analysis=negative,
    )
    _install_mock_composite(
        monkeypatch,
        positive_score=0.0,
        positive_strength=SignalStrength.NONE,
        negative_score=0.0,
        negative_strength=SignalStrength.NONE,
    )

    report = await run_calibration(
        settings,
        positive_trials=3,
        negative_trials=3,
        author=author.slug,
        seed=7,
        project_root=tmp_path,
        db_path=tmp_db,
    )

    assert report.sensitivity == pytest.approx(0.0)
    assert report.specificity == pytest.approx(1.0)
    assert report.precision == 0.0
    assert report.f1_score == 0.0


@pytest.mark.asyncio
async def test_calibration_dry_run_skips_everything(
    settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run path returns an empty report without touching the DB."""
    called = {"loader": 0}

    def fake_load_author_articles(db_path, slug):  # noqa: ARG001
        called["loader"] += 1
        raise AssertionError("dry-run should not load authors")

    monkeypatch.setattr(runner_mod, "_load_author_articles", fake_load_author_articles)

    report = await run_calibration(
        settings,
        positive_trials=2,
        negative_trials=2,
        project_root=tmp_path,
        db_path=tmp_path / "missing.db",
        dry_run=True,
    )
    assert report.trials == []
    assert called["loader"] == 0


def test_calibrate_cli_help_lists_flags() -> None:
    import re

    from typer.testing import CliRunner

    from forensics.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["calibrate", "--help"])
    assert result.exit_code == 0
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    for flag in ("--positive-trials", "--negative-trials", "--author", "--seed", "--dry-run"):
        assert flag in text, f"missing {flag} in calibrate --help"
