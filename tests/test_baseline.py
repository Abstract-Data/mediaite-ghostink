"""Phase 10 — unit tests for baseline generation + chain of custody.

Tests never touch a live Ollama instance.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from forensics.baseline import agent as agent_mod
from forensics.baseline import preflight as preflight_mod
from forensics.baseline import prompts as prompt_mod
from forensics.baseline import topics as topics_mod
from forensics.baseline import utils as bu
from forensics.config.settings import BaselineConfig, ChainOfCustodyConfig
from forensics.models import Article, Author
from forensics.utils.provenance import compute_corpus_hash, verify_corpus_hash

# --- utils --------------------------------------------------------------------


def test_sanitize_model_tag_handles_colon_and_slash() -> None:
    assert bu.sanitize_model_tag("llama3.1:8b") == "llama3.1-8b"
    assert bu.sanitize_model_tag("abc/def:ghi") == "abc-def-ghi"


def test_hash_prompt_text_deterministic() -> None:
    assert bu.hash_prompt_text("hello") == bu.hash_prompt_text("hello")
    assert bu.hash_prompt_text("a") != bu.hash_prompt_text("b")


# --- prompts ------------------------------------------------------------------


def test_build_prompt_renders_keywords_and_word_count(tmp_path: Path) -> None:
    (tmp_path / "prompts" / "baseline_templates").mkdir(parents=True)
    (tmp_path / "prompts" / "baseline_templates" / "raw_generation.txt").write_text(
        "Write {word_count} words about {topic_keywords} ({suggested_angle})",
        encoding="utf-8",
    )
    out = prompt_mod.build_prompt(
        "raw_generation",
        prompt_mod.PromptContext(
            topic_keywords=["trump", "election"],
            target_word_count=800,
            suggested_angle="focus on facts",
        ),
        project_root=tmp_path,
    )
    assert "800" in out
    assert "trump" in out
    assert "focus on facts" in out


def test_build_prompt_missing_template(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        prompt_mod.build_prompt(
            "nonexistent",
            prompt_mod.PromptContext(topic_keywords=["x"], target_word_count=100),
            project_root=tmp_path,
        )


def test_list_templates_reads_project_templates(tmp_path: Path) -> None:
    d = tmp_path / "prompts" / "baseline_templates"
    d.mkdir(parents=True)
    (d / "raw_generation.txt").write_text("x", encoding="utf-8")
    (d / "style_mimicry.txt").write_text("y", encoding="utf-8")
    assert set(prompt_mod.list_templates(tmp_path)) == {"raw_generation", "style_mimicry"}


# --- topics -------------------------------------------------------------------


def test_cycle_keywords_round_robins() -> None:
    out = topics_mod.cycle_keywords([["a"], ["b"]], 5)
    assert out == [["a"], ["b"], ["a"], ["b"], ["a"]]


def test_cycle_keywords_empty_falls_back_to_default() -> None:
    out = topics_mod.cycle_keywords([], 2)
    assert len(out) == 2
    assert all("politics" in kw for kw in out)


def test_sample_word_counts_uses_corpus(tmp_path: Path) -> None:
    from forensics.storage.repository import Repository, init_db

    db_path = tmp_path / "articles.db"
    init_db(db_path)
    repo = Repository(db_path)
    author = Author(
        id="aid",
        name="Fixture",
        slug="fixture-slug",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-slug/",
    )
    repo.upsert_author(author)
    for i, wc in enumerate([400, 800, 1000]):
        repo.upsert_article(
            Article(
                id=f"a-{i}",
                author_id=author.id,
                url=f"https://example.com/{i}",
                title=f"t{i}",
                published_date=datetime(2024, 1, i + 1, tzinfo=UTC),
                clean_text="x" * 5,
                word_count=wc,
                content_hash=f"h{i}",
            )
        )
    counts = topics_mod.sample_word_counts(db_path, "fixture-slug", 5, seed=7)
    assert len(counts) == 5
    assert all(c in {400, 800, 1000} for c in counts)


# --- agent (no Ollama) --------------------------------------------------------


def test_generated_article_autofills_word_count() -> None:
    art = agent_mod.GeneratedArticle(headline="H", text="one two three four", actual_word_count=0)
    assert art.with_auto_word_count().actual_word_count == 4


def test_make_baseline_agent_requires_pydantic_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _blocked(name, *a, **k):
        if name.startswith("pydantic_ai"):
            raise ImportError("pretend pydantic-ai is missing")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    with pytest.raises(ImportError, match="pydantic-ai"):
        agent_mod.make_baseline_agent("llama3.1:8b", "http://localhost:11434")


# --- preflight ----------------------------------------------------------------


def _patch_mock_transport(monkeypatch: pytest.MonkeyPatch, tags_payload: dict) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tags_payload)

    RealAsyncClient = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(preflight_mod.httpx, "AsyncClient", _factory)


def test_preflight_with_all_models(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    _patch_mock_transport(
        monkeypatch,
        {"models": [{"name": "llama3.1:8b"}, {"name": "mistral:7b"}]},
    )
    ok = asyncio.run(preflight_mod.preflight_check(["llama3.1:8b", "mistral:7b"], "http://x"))
    assert ok is True


def test_preflight_reports_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    _patch_mock_transport(monkeypatch, {"models": [{"name": "llama3.1:8b"}]})
    ok = asyncio.run(preflight_mod.preflight_check(["llama3.1:8b", "mistral:7b"], "http://x"))
    assert ok is False


# --- config defaults ----------------------------------------------------------


def test_baseline_config_defaults() -> None:
    cfg = BaselineConfig()
    assert cfg.ollama_base_url.startswith("http://")
    assert "llama3.1:8b" in cfg.models
    assert 0.0 in cfg.temperatures


def test_chain_of_custody_config_defaults() -> None:
    coc = ChainOfCustodyConfig()
    assert coc.verify_corpus_hash is True
    assert coc.verify_raw_archives is True


# --- chain of custody --------------------------------------------------------


def test_corpus_hash_deterministic(tmp_path: Path) -> None:
    from forensics.storage.repository import Repository, init_db

    db_path = tmp_path / "articles.db"
    init_db(db_path)
    repo = Repository(db_path)
    author = Author(
        id="aid",
        name="Fixture",
        slug="fixture-author",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-author/",
    )
    repo.upsert_author(author)
    repo.upsert_article(
        Article(
            id="a-1",
            author_id=author.id,
            url="https://example.com/1",
            title="t1",
            published_date=datetime(2024, 1, 1, tzinfo=UTC),
            clean_text="hello world",
            word_count=2,
            content_hash="abc123",
        )
    )
    h1 = compute_corpus_hash(db_path)
    h2 = compute_corpus_hash(db_path)
    assert h1 == h2


def test_verify_corpus_hash_detects_mismatch(tmp_path: Path) -> None:
    from forensics.storage.repository import Repository, init_db

    db_path = tmp_path / "articles.db"
    analysis_dir = tmp_path / "analysis"
    init_db(db_path)
    repo = Repository(db_path)
    author = Author(
        id="aid",
        name="Fixture",
        slug="fixture-author",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-author/",
    )
    repo.upsert_author(author)
    repo.upsert_article(
        Article(
            id="a-1",
            author_id=author.id,
            url="https://example.com/1",
            title="t1",
            published_date=datetime(2024, 1, 1, tzinfo=UTC),
            clean_text="hello world",
            word_count=2,
            content_hash="abc123",
        )
    )
    analysis_dir.mkdir()
    (analysis_dir / "corpus_custody.json").write_text(
        json.dumps({"corpus_hash": "deadbeef", "recorded_at": "2026-01-01"}),
        encoding="utf-8",
    )
    ok, msg = verify_corpus_hash(db_path, analysis_dir)
    assert ok is False
    assert "mismatch" in msg.lower()
