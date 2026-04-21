"""Phase 10: baseline generation, chain-of-custody, and eval harness."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import polars as pl
import pytest
from pydantic import HttpUrl
from pydantic_ai.models.test import TestModel
from pydantic_evals import Case
from pydantic_evals.evaluators import EvaluatorContext

from forensics.baseline.agent import make_baseline_agent, run_generation_matrix
from forensics.baseline.custody import verify_raw_archive_integrity
from forensics.baseline.eval_quality import (
    BaselineInput,
    BaselineOutput,
    RepetitionDetector,
    TopicRelevance,
    WordCountAccuracy,
    baseline_eval_dataset,
)
from forensics.baseline.generation import BaselineGenerationConfig
from forensics.baseline.io import article_json_path, cell_dir_name, write_article_json
from forensics.baseline.models import BaselineDeps, GeneratedArticle
from forensics.baseline.ollama_client import fetch_model_digests, get_model_digest, preflight_check
from forensics.baseline.prompts import build_prompt, read_baseline_templates_for_manifest
from forensics.baseline.readme import generate_baseline_readme
from forensics.baseline.style_context import author_style_context
from forensics.baseline.topics import get_topic_distribution
from forensics.baseline.word_sampling import sample_word_counts
from forensics.models import Article, Author
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository, init_db, insert_analysis_run
from forensics.utils.provenance import audit_scrape_timestamps, compute_corpus_hash


def _politics_text(i: int) -> str:
    return (
        f"Washington political news continues as Congress debates policy {i}. "
        "Sources say the administration is weighing options while the opposition "
        "criticizes timing. Analysts expect further developments next week."
    )


def test_topic_distribution_extraction(
    tmp_db: Path, sample_author: Author, forensics_config_path: Path
) -> None:
    _ = forensics_config_path
    repo = Repository(tmp_db)
    repo.upsert_author(sample_author)
    for i in range(8):
        url = f"https://www.mediaite.com/2024/01/{i:02d}/story-{i}/"
        a = Article(
            id=stable_article_id(url),
            author_id=sample_author.id,
            url=HttpUrl(url),
            title=f"Story {i}",
            published_date=datetime(2024, 1, i + 1, tzinfo=UTC),
            clean_text=_politics_text(i) * 3,
            word_count=120 + i * 5,
            content_hash=f"h{i}",
            scraped_at=datetime(2024, 2, 1, tzinfo=UTC),
        )
        repo.upsert_article(a)
    dist = get_topic_distribution(sample_author.slug, tmp_db, num_topics=5, n_keywords=5)
    assert len(dist) >= 2
    assert abs(sum(t["weight"] for t in dist) - 1.0) < 1e-6


def test_word_count_sampling() -> None:
    df = pl.DataFrame({"word_count": [100, 200, 300, 400]})
    out = sample_word_counts(df, 20, seed=7)
    assert len(out) == 20
    assert all(w in (100, 200, 300, 400) for w in out)


def test_generation_manifest_schema() -> None:
    manifest = {
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T01:00:00+00:00",
        "authors": ["fixture-author"],
        "models": [{"name": "llama3.1:8b", "digest": "sha256:x", "notes": "n"}],
        "temperatures": [0.0, 0.8],
        "prompt_templates": ["raw_generation", "style_mimicry"],
        "articles_per_cell": 30,
        "max_tokens": 1500,
        "article_count": 360,
        "dry_run": False,
        "raw_template": "x",
        "mimicry_template": "y",
    }
    for k in (
        "started_at",
        "completed_at",
        "authors",
        "models",
        "temperatures",
        "prompt_templates",
        "articles_per_cell",
        "max_tokens",
        "article_count",
    ):
        assert k in manifest


def test_article_json_schema() -> None:
    payload = {
        "headline": "Test",
        "text": "word " * 60,
        "actual_word_count": 60,
    }
    g = GeneratedArticle.model_validate(payload)
    assert g.actual_word_count == 60


def test_baseline_readme_generation(tmp_path: Path) -> None:
    manifest = {
        "completed_at": "2026-01-01",
        "authors": ["a"],
        "article_count": 3,
        "models": [{"name": "m", "digest": "d", "notes": ""}],
        "temperatures": [0.0],
        "prompt_templates": ["raw_generation"],
        "articles_per_cell": 1,
        "max_tokens": 100,
        "raw_template": "RAW",
        "mimicry_template": "MIM",
    }
    p = tmp_path / "README.md"
    generate_baseline_readme(manifest, p)
    text = p.read_text(encoding="utf-8")
    assert "AI baseline corpus" in text
    assert "RAW" in text


def test_corpus_hash_deterministic(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, content_hash TEXT NOT NULL)",
    )
    conn.execute("INSERT INTO articles(content_hash) VALUES ('a'), ('b')")
    conn.commit()
    conn.close()
    assert compute_corpus_hash(db) == compute_corpus_hash(db)
    assert len(compute_corpus_hash(db)) == 64


def test_corpus_hash_changes(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, content_hash TEXT NOT NULL)",
    )
    conn.execute("INSERT INTO articles(content_hash) VALUES ('x')")
    conn.commit()
    conn.close()
    h1 = compute_corpus_hash(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO articles(content_hash) VALUES ('y')")
    conn.commit()
    conn.close()
    assert compute_corpus_hash(db) != h1


def test_scrape_timestamp_audit(
    tmp_db: Path, sample_author: Author, sample_article: Article
) -> None:
    repo = Repository(tmp_db)
    repo.upsert_author(sample_author)
    a = sample_article.model_copy(
        update={
            "clean_text": "hello world",
            "word_count": 2,
            "content_hash": "z",
            "scraped_at": datetime(2024, 3, 1, tzinfo=UTC),
        },
    )
    repo.upsert_article(a)
    aud = audit_scrape_timestamps(tmp_db)
    assert aud["total_articles"] == 1
    assert aud["articles_with_scraped_at"] == 1


@pytest.mark.asyncio
async def test_dry_run_no_ollama_calls(
    tmp_path: Path, sample_author: Author, forensics_config_path: Path
) -> None:
    _ = forensics_config_path
    init_db(tmp_path / "articles.db")
    repo = Repository(tmp_path / "articles.db")
    repo.upsert_author(sample_author)
    for i in range(8):
        url = f"https://www.mediaite.com/2024/02/{i:02d}/dry-{i}/"
        a = Article(
            id=stable_article_id(url),
            author_id=sample_author.id,
            url=HttpUrl(url),
            title=f"Dry {i}",
            published_date=datetime(2024, 2, i + 1, tzinfo=UTC),
            clean_text=_politics_text(i) * 2,
            word_count=200,
            content_hash=f"d{i}",
            scraped_at=datetime(2024, 3, 1, tzinfo=UTC),
        )
        repo.upsert_article(a)
    td = get_topic_distribution(sample_author.slug, tmp_path / "articles.db")
    arts = repo.list_articles_for_extraction(author_id=sample_author.id)
    wc_frame = pl.DataFrame({"word_count": [a.word_count for a in arts]})
    cfg = BaselineGenerationConfig(
        ollama_base_url="http://localhost:11434",
        models=[
            {"name": "llama3.1:8b", "provider": "ollama", "family": "x", "size_gb": 1, "notes": ""}
        ],
        temperatures=[0.0],
        articles_per_cell=2,
        max_tokens=100,
        request_timeout=30.0,
        output_dir=tmp_path / "out",
        log_generations=False,
    )
    with patch("forensics.baseline.agent.make_baseline_agent") as mock_make:
        plan = await run_generation_matrix(
            sample_author.slug,
            cfg,
            topic_distribution=td,
            style_context={"suggested_angle": "x"},
            word_count_frame=wc_frame,
            dry_run=True,
        )
        mock_make.assert_not_called()
    assert plan and plan[0].get("dry_run") is True


@pytest.mark.asyncio
async def test_preflight_check_missing_model() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"models": [{"name": "other:1b"}]})

    class FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, *a, **k) -> MagicMock:
            return mock_resp

    with patch("httpx.AsyncClient", FakeClient):
        ok = await preflight_check(["llama3.1:8b"], ollama_base_url="http://localhost:11434")
    assert ok is False


def test_model_digest_captured() -> None:
    d = get_model_digest("llama3.1:8b", {"llama3.1:8b": "abc123deadbeef"})
    assert d.startswith("sha256:")


def test_insert_analysis_run_corpus_hash(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    init_db(db)
    rid = insert_analysis_run(db, config_hash="x", description="t", input_corpus_hash="dead" * 8)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT input_corpus_hash FROM analysis_runs WHERE id = ?",
        (rid,),
    ).fetchone()
    conn.close()
    assert row[0] == "dead" * 8


@pytest.mark.asyncio
async def test_agent_returns_generated_article() -> None:
    agent = make_baseline_agent("llama3.1:8b")
    body = ("word " * 500).strip()
    custom = {"headline": "Political update", "text": body, "actual_word_count": 500}
    async with httpx.AsyncClient(timeout=30.0) as client:
        deps = BaselineDeps(
            author_slug="test-author",
            topic_keywords=["politics", "election"],
            target_word_count=500,
            prompt_template="raw_generation",
            temperature=0.0,
            output_dir=Path("/tmp/test-baseline"),
            http_client=client,
        )
        with agent.override(model=TestModel(custom_output_args=custom)):
            result = await agent.run("Write an article about politics.", deps=deps)
    assert isinstance(result.output, GeneratedArticle)


def test_eval_dataset_schema() -> None:
    assert baseline_eval_dataset.name == "baseline_quality"
    assert isinstance(baseline_eval_dataset.cases[0], Case)


def test_word_count_evaluator() -> None:
    from pydantic_evals.otel._errors import SpanTreeRecordingError

    ev = WordCountAccuracy()
    ctx = EvaluatorContext(
        name="c",
        inputs=BaselineInput(
            topic_keywords=["a"],
            target_word_count=100,
            prompt_template="raw_generation",
            temperature=0.0,
        ),
        metadata=None,
        expected_output=None,
        output=BaselineOutput(headline="h", text="x " * 50, actual_word_count=100),
        duration=0.0,
        _span_tree=SpanTreeRecordingError(),
        attributes={},
        metrics={},
    )
    assert ev.evaluate(ctx) == 1.0


def test_topic_relevance_evaluator() -> None:
    from pydantic_evals.otel._errors import SpanTreeRecordingError

    ev = TopicRelevance()
    ctx_ok = EvaluatorContext(
        name="c",
        inputs=BaselineInput(
            topic_keywords=["fox", "news"],
            target_word_count=50,
            prompt_template="raw_generation",
            temperature=0.0,
        ),
        metadata=None,
        expected_output=None,
        output=BaselineOutput(
            headline="h", text="The fox ran across the news desk.", actual_word_count=8
        ),
        duration=0.0,
        _span_tree=SpanTreeRecordingError(),
        attributes={},
        metrics={},
    )
    assert ev.evaluate(ctx_ok) > 0.0


def test_repetition_detector() -> None:
    from pydantic_evals.otel._errors import SpanTreeRecordingError

    ev = RepetitionDetector()
    rep = "Same. " * 10
    ctx_bad = EvaluatorContext(
        name="c",
        inputs=BaselineInput(
            topic_keywords=["a"],
            target_word_count=20,
            prompt_template="raw_generation",
            temperature=0.0,
        ),
        metadata=None,
        expected_output=None,
        output=BaselineOutput(headline="h", text=rep, actual_word_count=20),
        duration=0.0,
        _span_tree=SpanTreeRecordingError(),
        attributes={},
        metrics={},
    )
    assert ev.evaluate(ctx_bad) == 0.0


def test_verify_raw_archive_skips_without_raw(tmp_path: Path) -> None:
    assert verify_raw_archive_integrity(tmp_path) is True


def test_verify_raw_archive_flags_stale_tar(tmp_path: Path, sample_author: Author) -> None:
    root = tmp_path / "data"
    root.mkdir()
    db = root / "articles.db"
    init_db(db)
    (root / "raw").mkdir()
    tar = root / "raw" / "2023.tar.gz"
    tar.write_bytes(b"x")
    old_ts = datetime(2019, 6, 1, tzinfo=UTC).timestamp()
    os.utime(tar, (old_ts, old_ts))

    repo = Repository(db)
    repo.upsert_author(sample_author)
    url = "https://www.mediaite.com/2023/06/01/archive-row/"
    a = Article(
        id=stable_article_id(url),
        author_id=sample_author.id,
        url=HttpUrl(url),
        title="Archive row",
        published_date=datetime(2023, 6, 1, tzinfo=UTC),
        raw_html_path="raw/2023.tar.gz:entry1",
        clean_text="Body.",
        word_count=2,
        content_hash="c1",
        scraped_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    repo.upsert_article(a)
    assert verify_raw_archive_integrity(root) is False


def test_verify_raw_archive_skips_bad_scrape_ts(
    tmp_path: Path, sample_author: Author
) -> None:
    root = tmp_path / "data2"
    root.mkdir()
    db = root / "articles.db"
    init_db(db)
    (root / "raw").mkdir()
    tar = root / "raw" / "2022.tar.gz"
    tar.write_bytes(b"x")
    repo = Repository(db)
    repo.upsert_author(sample_author)
    url = "https://www.mediaite.com/2022/01/01/bad-ts/"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO articles (
            id, author_id, url, title, published_date, raw_html_path,
            clean_text, word_count, content_hash, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stable_article_id(url),
            sample_author.id,
            str(HttpUrl(url)),
            "t",
            "2022-01-01T00:00:00+00:00",
            "raw/2022.tar.gz:x",
            "x",
            1,
            "h",
            "not-a-valid-iso",
        ),
    )
    conn.commit()
    conn.close()
    assert verify_raw_archive_integrity(root) is True


def test_read_baseline_templates_for_manifest() -> None:
    raw_t, mimic_t = read_baseline_templates_for_manifest()
    assert "word" in raw_t.lower() or "article" in raw_t.lower()
    assert len(mimic_t) > 20


def test_build_prompt_raw_and_mimicry() -> None:
    deps = BaselineDeps(
        author_slug="a",
        topic_keywords=["politics", "media"],
        target_word_count=420,
        prompt_template="raw_generation",
        temperature=0.0,
        output_dir=Path("/tmp"),
        http_client=MagicMock(),
    )
    style = {
        "suggested_angle": "committee markup",
        "outlet_name": "Test Outlet",
        "topic_area": "Capitol Hill",
        "author_avg_sentence_length": "20",
        "author_tone_description": "sharp",
        "author_structure_notes": "lede then nut graf",
    }
    raw_p = build_prompt("raw_generation", deps, style_context=style)
    assert "420" in raw_p and "politics" in raw_p and "committee" in raw_p
    mimic_p = build_prompt("style_mimicry", deps, style_context=style)
    assert "Test Outlet" in mimic_p and "420" in mimic_p


def test_build_prompt_unknown_template() -> None:
    deps = BaselineDeps(
        author_slug="a",
        topic_keywords=["x"],
        target_word_count=100,
        prompt_template="raw_generation",
        temperature=0.0,
        output_dir=Path("/tmp"),
        http_client=MagicMock(),
    )
    with pytest.raises(ValueError, match="Unknown prompt template"):
        build_prompt("other", deps, style_context={})


def test_cell_dir_name_and_write_article_json(tmp_path: Path) -> None:
    assert cell_dir_name("raw_generation", 0.8) == "raw_t0.8"
    assert cell_dir_name("style_mimicry", 0.0) == "mimicry_t0.0"
    p = article_json_path(
        "auth",
        tmp_path,
        "llama3.1:8b",
        "raw_generation",
        0.0,
        7,
    )
    assert p.name == "article_007.json"
    write_article_json(p, {"headline": "H", "text": "word " * 60, "actual_word_count": 60})
    loaded = p.read_text(encoding="utf-8")
    assert "headline" in loaded


def test_author_style_context(tmp_db: Path, sample_author: Author) -> None:
    repo = Repository(tmp_db)
    repo.upsert_author(sample_author)
    sent = "First sentence here. Second sentence follows. Third wraps it up."
    for i in range(3):
        url = f"https://www.mediaite.com/2023/03/{i:02d}/ctx-{i}/"
        a = Article(
            id=stable_article_id(url),
            author_id=sample_author.id,
            url=HttpUrl(url),
            title=f"C{i}",
            published_date=datetime(2023, 3, i + 1, tzinfo=UTC),
            clean_text=sent,
            word_count=12,
            content_hash=f"c{i}",
            scraped_at=datetime(2023, 4, 1, tzinfo=UTC),
        )
        repo.upsert_article(a)
    ctx = author_style_context(sample_author.slug, tmp_db)
    assert ctx["outlet_name"] == "mediaite.com"
    assert "author_avg_sentence_length" in ctx


def test_author_style_context_unknown_author(tmp_db: Path) -> None:
    with pytest.raises(ValueError, match="Unknown author slug"):
        author_style_context("no-such-slug", tmp_db)


@pytest.mark.asyncio
async def test_preflight_ollama_connect_error() -> None:
    class BoomClient:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> BoomClient:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, *a, **k) -> None:
            raise httpx.ConnectError("nope", request=MagicMock())

    with patch("httpx.AsyncClient", BoomClient):
        ok = await preflight_check(["llama3.1:8b"], ollama_base_url="http://localhost:11434")
    assert ok is False


@pytest.mark.asyncio
async def test_fetch_model_digests_ok() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(
        return_value={
            "models": [
                {"name": "m1:latest", "digest": "abc"},
                {"name": "m2:latest", "digest": ""},
            ],
        },
    )

    class FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, *a, **k) -> MagicMock:
            return mock_resp

    with patch("httpx.AsyncClient", FakeClient):
        m = await fetch_model_digests("http://localhost:11434", timeout=1.0)
    assert m["m1:latest"] == "abc"
    assert m["m2:latest"] == ""


def test_extract_baseline_features_empty(tmp_path: Path, settings) -> None:
    import spacy

    from forensics.baseline.features import extract_baseline_features

    try:
        spacy.load("en_core_web_md")
    except OSError:
        pytest.skip("en_core_web_md not installed")

    root = tmp_path / "ai_baseline"
    root.mkdir()
    out = extract_baseline_features(root, settings)
    assert out == {}
