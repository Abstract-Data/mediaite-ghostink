"""Feature extraction unit tests (Phase 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from forensics.models import Article, Author
from forensics.storage.repository import Repository, init_db


def _long_text() -> str:
    base = (
        "The quick brown fox jumps over the lazy dog. "
        "It's important to note that we delve into many topics. "
        "Perhaps it seems likely that one could argue otherwise. "
    )
    return (base * 8)[:]


@pytest.fixture(scope="module")
def nlp():
    pytest.importorskip("spacy")
    import spacy

    try:
        return spacy.load("en_core_web_md")
    except OSError:
        pytest.skip("en_core_web_md not installed (uv run python -m spacy download en_core_web_md)")


def test_ttr_calculation(nlp) -> None:
    from forensics.features import lexical

    text = "cat cat dog bird"
    doc = nlp(text)
    out = lexical.extract_lexical_features(text, doc)
    assert out["ttr"] == pytest.approx(3 / 4)


def test_mattr_window(nlp) -> None:
    from forensics.features import lexical

    words = " ".join([f"w{i}" for i in range(60)])
    doc = nlp(words)
    out = lexical.extract_lexical_features(words, doc)
    assert out["mattr"] == pytest.approx(1.0, rel=1e-2)


def test_hapax_ratio(nlp) -> None:
    from forensics.features import lexical

    text = "only once repeats repeats"
    doc = nlp(text)
    out = lexical.extract_lexical_features(text, doc)
    assert out["hapax_ratio"] == pytest.approx(0.5)


def test_ai_marker_detection(nlp) -> None:
    from forensics.features import lexical

    text = "It's important to note. We should delve deeper. " * 5
    doc = nlp(text)
    out = lexical.extract_lexical_features(text, doc)
    assert out["ai_marker_frequency"] > 0


def test_pos_bigram_extraction(nlp) -> None:
    from forensics.features import pos_patterns

    doc = nlp("The cat sat.")
    out = pos_patterns.extract_pos_pattern_features(doc)
    assert any("DET" in k for k in out["pos_bigram_top30"])


def test_pos_bigram_normalization(nlp) -> None:
    from forensics.features import pos_patterns

    doc = nlp("The cat sat on the mat.")
    out = pos_patterns.extract_pos_pattern_features(doc)
    s = sum(out["pos_bigram_top30"].values())
    assert s == pytest.approx(1.0, rel=1e-5) or s == 0.0


def test_clause_initial_entropy(nlp) -> None:
    from forensics.features import pos_patterns

    boring = " ".join(["The cat sat."] * 10)
    diverse = "Suddenly, chaos erupted. Why bother? Running fast, she left. " * 3
    e_low = pos_patterns.extract_pos_pattern_features(nlp(boring))["clause_initial_entropy"]
    e_high = pos_patterns.extract_pos_pattern_features(nlp(diverse))["clause_initial_entropy"]
    assert e_high >= e_low


def test_dep_depth_known_sentence(nlp) -> None:
    from forensics.features import pos_patterns

    doc = nlp("The cat sat on the mat.")
    out = pos_patterns.extract_pos_pattern_features(doc)
    assert out["dep_depth_max"] >= 0


def test_sentence_stats(nlp) -> None:
    from forensics.features import structural

    text = "One. Two words. Three little words here."
    doc = nlp(text)
    out = structural.extract_structural_features(text, doc)
    assert out["sent_length_mean"] > 0


def test_passive_voice_detection(nlp) -> None:
    from forensics.features import structural

    passive = nlp("The ball was thrown.")
    active = nlp("He threw the ball.")
    assert structural.extract_structural_features(passive.text, passive)["passive_voice_ratio"] > 0
    assert structural.extract_structural_features(active.text, active)["passive_voice_ratio"] == 0


def test_punctuation_profile(nlp) -> None:
    from forensics.features import structural

    text = 'Hi; there: (yes)! — "wow"...'
    doc = nlp(text)
    out = structural.extract_structural_features(text, doc)
    assert out["punctuation_profile"][";"] > 0


def test_bigram_entropy(nlp) -> None:
    from forensics.features import content

    rep = "foo bar " * 40
    diverse = " ".join([f"w{i}" for i in range(80)])
    doc_r = nlp(rep)
    doc_d = nlp(diverse)
    er = content.extract_content_features(rep, doc_r, [], [])
    ed = content.extract_content_features(diverse, doc_d, [], [])
    assert er["bigram_entropy"] < ed["bigram_entropy"]


def test_self_similarity(nlp) -> None:
    from forensics.features import content

    t = "identical text " * 20
    doc = nlp(t)
    sim = content.extract_content_features(t, doc, [t, t], [t, t])
    assert sim["self_similarity_30d"] == pytest.approx(1.0, abs=0.05)


def test_readability_scores() -> None:
    from forensics.features import readability

    text = (
        "The National Institute for Health and Care Excellence issued guidance. "
        "Schools remained open during the winter term for most pupils."
    ) * 3
    out = readability.extract_readability_features(text)
    assert not np.isnan(out["flesch_kincaid"])


def test_embedding_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from forensics.features import embeddings as emb

    class _FakeModel:
        def encode(self, text: str, show_progress_bar: bool = False) -> np.ndarray:
            return np.zeros(384, dtype=np.float32)

    monkeypatch.setattr(emb, "_MODEL_CACHE", {})
    monkeypatch.setattr(emb, "_get_model", lambda name: _FakeModel())
    vec = emb.compute_embedding("hello", "fake-model")
    assert vec.shape == (384,)


def test_list_articles_for_extraction(tmp_path: Path, sample_author: Author) -> None:
    db_path = tmp_path / "articles.db"
    init_db(db_path)
    url = "https://www.mediaite.com/2024/01/02/extract-test/"
    body = _long_text()
    a_ok = Article(
        id="a-ok",
        author_id=sample_author.id,
        url=url,
        title="Ok",
        published_date=datetime(2024, 1, 2, tzinfo=UTC),
        clean_text=body,
        word_count=len(body.split()),
        content_hash="h1",
    )
    a_short = Article(
        id="a-short",
        author_id=sample_author.id,
        url="https://www.mediaite.com/2024/01/03/short/",
        title="Short",
        published_date=datetime(2024, 1, 3, tzinfo=UTC),
        clean_text="word " * 10,
        word_count=10,
        content_hash="h2",
    )
    a_redirect = Article(
        id="a-redir",
        author_id=sample_author.id,
        url="https://www.mediaite.com/2024/01/04/redir/",
        title="R",
        published_date=datetime(2024, 1, 4, tzinfo=UTC),
        clean_text="[REDIRECT:example.com] " + body,
        word_count=200,
        content_hash="h3",
    )
    a_dup = Article(
        id="a-dup",
        author_id=sample_author.id,
        url="https://www.mediaite.com/2024/01/05/dup/",
        title="Dup",
        published_date=datetime(2024, 1, 5, tzinfo=UTC),
        clean_text=body,
        word_count=len(body.split()),
        content_hash="h4",
        is_duplicate=True,
    )
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        for a in (a_ok, a_short, a_redirect, a_dup):
            repo.upsert_article(a)
        rows = repo.list_articles_for_extraction()
    assert len(rows) == 1 and rows[0].id == "a-ok"


def test_get_author_by_slug(tmp_path: Path, sample_author: Author) -> None:
    db_path = tmp_path / "articles.db"
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        found = repo.get_author_by_slug("test-author")
    assert found is not None and found.id == sample_author.id


def test_feature_pipeline_isolation(
    tmp_path: Path,
    sample_author: Author,
    forensics_config_path: Path,
    nlp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from forensics.config import get_settings
    from forensics.features import lexical as lex_mod
    from forensics.features import pipeline as pl

    get_settings.cache_clear()
    db_path = tmp_path / "articles.db"
    init_db(db_path)
    good = _long_text()
    orig_lex = lex_mod.extract_lexical_features
    calls = {"n": 0}

    def flaky(text: str, doc) -> dict:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated failure")
        return orig_lex(text, doc)

    monkeypatch.setattr(lex_mod, "extract_lexical_features", flaky)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        for i in range(3):
            url = f"https://www.mediaite.com/2024/02/{i + 1:02d}/p/"
            a = Article(
                id=f"art-{i}",
                author_id=sample_author.id,
                url=url,
                title=f"T{i}",
                published_date=datetime(2024, 2, i + 1, tzinfo=UTC),
                clean_text=good,
                word_count=len(good.split()),
                content_hash=f"h{i}",
            )
            repo.upsert_article(a)

    monkeypatch.setattr("forensics.features.pipeline.spacy.load", lambda name: nlp)
    n = pl.extract_all_features(
        db_path,
        get_settings(),
        skip_embeddings=True,
        project_root=tmp_path,
    )
    assert n == 2


def test_nan_handling(nlp) -> None:
    from forensics.features import lexical

    text = "### !!!"
    doc = nlp(text)
    out = lexical.extract_lexical_features(text, doc)
    assert np.isnan(out["ttr"])


def test_productivity_rolling(tmp_path: Path) -> None:
    from forensics.features import productivity

    base = datetime(2024, 1, 10, tzinfo=UTC)
    prior: list[tuple[datetime, int]] = sorted(
        [
            (base - timedelta(days=1), 100),
            (base - timedelta(days=2), 200),
        ],
        key=lambda x: x[0],
    )
    out = productivity.extract_productivity_features(base, 300, prior)
    assert out["rolling_7d_count"] >= 2
    assert out["days_since_last_article"] == pytest.approx(1.0, rel=0.01)


def test_write_features_roundtrip(tmp_path: Path, sample_author: Author) -> None:
    from forensics.models.features import FeatureVector
    from forensics.storage.parquet import read_features, write_features

    fv = FeatureVector(
        article_id="x",
        author_id=sample_author.id,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        function_word_distribution={"the": 0.5},
        punctuation_profile={";": 0.1},
        pos_bigram_top30={"DET_NOUN": 0.2},
        clause_initial_top10={"DET_NOUN_VERB": 0.1},
    )
    path = tmp_path / "f.parquet"
    write_features([fv], path)
    df = read_features(path)
    assert df.height == 1
    assert "article_id" in df.columns
