"""End-to-end pipeline smoke: seeded DB → extract → analyze → optional Quarto report.

Scrape is not invoked; the SQLite corpus is built in-process. Network is unused.

When ``quarto`` is on ``PATH``, renders ``index.qmd`` into ``data/reports/`` after
analysis prerequisites pass. CI images without Quarto still validate extract +
analysis + ``comparison_report.json`` (the target-role regression gate).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from forensics.analysis.orchestrator import run_full_analysis
from forensics.config import get_settings
from forensics.features.pipeline import extract_all_features
from forensics.models import Article, Author
from forensics.models.analysis import AnalysisResult, HypothesisTest
from forensics.models.report_args import ReportArgs
from forensics.paths import AnalysisArtifactPaths
from forensics.reporting import run_report
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository, init_db

_FIXTURE_CONFIG = Path(__file__).resolve().parent / "fixtures" / "e2e" / "config.toml"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _lorem_paragraph(seed: int) -> str:
    """Deterministic ~70-token paragraph so ``word_count >= 50`` for extraction."""
    base = (
        "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
        "incididunt ut labore et dolore magna aliqua ut enim ad minim veniam quis nostrud "
        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat duis aute "
        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat "
        "nulla pariatur excepteur sint occaecat cupidatat non proident sunt in culpa qui "
        "officia deserunt mollit anim id est laborum curabitur pretium tincidunt lacus "
        "cras ornare tristique elit integer nec odio praesent libero sed cursus ante "
        "dapibus diam sed nisi nulla quis sem at nibh elementum imperdiet duis sagittis "
        "ipsum praesent mauris fusce nec tellus sed augue semper porta mauris massa "
        "vestibulum lacinia arcu eget nulla class aptent taciti sociosqu ad litora "
        "torquent per conubia nostra inceptos himenaeos curabitur sodales ligula in libero "
        "sed dignissim lacinia nunc curabitur tortor pellentesque nibh aenean quam "
        "egestas semper aenean ultricies mi vitae est mauris placerat eleifend leo quisque "
        "vulputate magna eros eu erat aliquam erat volutpat nam dui mi tincidunt quis "
        "accumsan porttitor ac cursus eleifend elit."
    )
    return f"{base} segment={seed}"


def _seed_corpus(db_path: Path) -> None:
    """Two authors, ~30 dated articles each (2020–2024) for changepoint/hypothesis paths."""
    target = Author(
        id="author-fixture-target",
        name="Fixture Target",
        slug="fixture-target",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2024, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-target/",
    )
    control = Author(
        id="author-fixture-control",
        name="Fixture Control",
        slug="fixture-control",
        outlet="mediaite.com",
        role="control",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2024, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-control/",
    )
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.ensure_schema()
        repo.upsert_author(target)
        repo.upsert_author(control)
        start = datetime(2020, 1, 10, 12, 0, 0, tzinfo=UTC)
        for i in range(30):
            pub = start + timedelta(days=55 * i)
            for slug, author in (
                ("fixture-target", target),
                ("fixture-control", control),
            ):
                url = f"https://www.mediaite.com/politics/{slug}-article-{i:03d}/"
                body = _lorem_paragraph(i) + f" author={slug} idx={i}."
                wc = len(body.split())
                aid = stable_article_id(url)
                h = hashlib.sha256(body.encode()).hexdigest()
                art = Article(
                    id=aid,
                    author_id=author.id,
                    url=url,
                    title=f"{slug} headline {i}",
                    published_date=pub,
                    clean_text=body,
                    word_count=wc,
                    content_hash=h,
                )
                repo.upsert_article(art)


@pytest.mark.integration
@pytest.mark.slow
def test_pipeline_extract_analyze_comparison_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e2e_root = tmp_path / "workspace"
    (e2e_root / "data").mkdir(parents=True)
    cfg_dest = e2e_root / "config.toml"
    shutil.copyfile(_FIXTURE_CONFIG, cfg_dest)
    shutil.copyfile(_REPO_ROOT / "index.qmd", e2e_root / "index.qmd")
    shutil.copyfile(_REPO_ROOT / "quarto.yml", e2e_root / "quarto.yml")

    db_path = e2e_root / "data" / "articles.db"
    _seed_corpus(db_path)

    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg_dest))

    def _fake_project_root() -> Path:
        return e2e_root

    _settings_mod = importlib.import_module("forensics.config.settings")
    monkeypatch.setattr(_settings_mod, "_project_root", _fake_project_root)
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.db_path == db_path

    n = extract_all_features(
        db_path,
        settings,
        skip_embeddings=True,
        project_root=e2e_root,
        show_rich_progress=False,
    )
    assert n > 0

    paths = AnalysisArtifactPaths.from_project(e2e_root, db_path)
    for slug in ("fixture-target", "fixture-control"):
        p = paths.features_parquet(slug)
        assert p.is_file(), f"missing features parquet for {slug}"
        frame = pl.read_parquet(p)
        assert "ttr" in frame.columns
        assert "flesch_kincaid" in frame.columns

    results = run_full_analysis(paths, settings, exploratory=True, max_workers=1)
    assert "fixture-target" in results
    assert "fixture-control" in results

    target_result_path = paths.result_json("fixture-target")
    assert target_result_path.is_file()
    AnalysisResult.model_validate_json(target_result_path.read_text(encoding="utf-8"))

    hyp_path = paths.hypothesis_tests_json("fixture-target")
    assert hyp_path.is_file()
    hyp_raw = json.loads(hyp_path.read_text(encoding="utf-8"))
    assert isinstance(hyp_raw, list)
    if hyp_raw:
        HypothesisTest.from_legacy(hyp_raw[0])

    comparison_path = paths.comparison_report_json()
    assert comparison_path.is_file()
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    targets = comparison.get("targets") or {}
    assert isinstance(targets, dict)
    assert "fixture-target" in targets
    assert targets["fixture-target"], "comparison targets.fixture-target must be non-empty"

    monkeypatch.setattr("forensics.reporting.get_project_root", _fake_project_root)
    quarto = shutil.which("quarto")
    if quarto is None:
        return
    code = run_report(
        ReportArgs(
            notebook="index.qmd",
            report_format="html",
            verify=False,
        )
    )
    assert code == 0
    reports_dir = e2e_root / "data" / "reports"
    assert reports_dir.is_dir()
    assert any(reports_dir.iterdir()), (
        "quarto should write at least one artifact under data/reports/"
    )
