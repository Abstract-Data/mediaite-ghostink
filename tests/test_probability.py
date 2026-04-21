"""Phase 9 — unit + integration tests for probability features."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from forensics.config.settings import ForensicsSettings
from forensics.features import binoculars as bino_mod
from forensics.features import probability as prob
from forensics.features import probability_pipeline as pp
from forensics.models import Article, Author

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# --- pure helpers (no model needed) ----------------------------------------


def test_split_sentences_basic() -> None:
    text = 'First sentence. Second one! Third? "Quoted start" continues.'
    sents = prob.split_sentences(text)
    assert len(sents) >= 3
    assert "First sentence." in sents[0]


def test_split_sentences_empty_and_trivial() -> None:
    assert prob.split_sentences("") == []
    assert prob.split_sentences("   ") == []
    assert prob.split_sentences("single") == ["single"]


# --- fake model / tokenizer ---------------------------------------------------


@dataclass
class _FakeTensor:
    data: list[list[int]]
    _ndevice: str = "cpu"

    def size(self, dim: int) -> int:
        if dim == 0:
            return len(self.data)
        return len(self.data[0]) if self.data else 0

    def to(self, device: str) -> _FakeTensor:
        self._ndevice = device
        return self

    def clone(self) -> _FakeTensor:
        return _FakeTensor([row[:] for row in self.data], self._ndevice)

    def __setitem__(self, _key, _value) -> None:
        return None


class _FakeTokenizer:
    def __call__(self, text: str, return_tensors: str = "pt", **kw) -> dict:
        tokens = [ord(c) % 50 for c in (text or "")[:200]] or [0]
        return {"input_ids": _FakeTensor([tokens])}


class _FakeLoss:
    def __init__(self, value: float) -> None:
        self._v = value

    def __mul__(self, other: float) -> _FakeLoss:
        return _FakeLoss(self._v * float(other))

    def __add__(self, other: _FakeLoss) -> _FakeLoss:
        return _FakeLoss(self._v + other._v)


class _FakeOutputs:
    def __init__(self, loss_value: float) -> None:
        self.loss = _FakeLoss(loss_value)


class _FakeModel:
    def __init__(self, loss_value: float = 2.0) -> None:
        self._loss = loss_value
        self._device = "cpu"

    def parameters(self):
        import torch

        yield torch.zeros(1)

    def eval(self) -> _FakeModel:
        return self

    def to(self, _device: str) -> _FakeModel:
        return self

    def __call__(self, input_ids: Any, labels: Any | None = None) -> _FakeOutputs:
        return _FakeOutputs(self._loss)


# --- compute_perplexity with stubbed internals --------------------------------


def test_compute_perplexity_returns_all_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub the inner helper so we don't need a real model forward pass.
    monkeypatch.setattr(prob, "_perplexity_of_ids", lambda ids, m, **kw: 12.5)
    out = prob.compute_perplexity(
        "First sentence is fine. Another sentence follows here. And a third one too.",
        model=_FakeModel(),
        tokenizer=_FakeTokenizer(),
        max_length=32,
        stride=16,
        low_ppl_threshold=15.0,
    )
    expected_keys = {
        "mean_perplexity",
        "median_perplexity",
        "perplexity_variance",
        "min_sentence_ppl",
        "max_sentence_ppl",
        "ppl_skewness",
        "low_ppl_sentence_ratio",
    }
    assert expected_keys <= set(out)
    assert out["mean_perplexity"] == pytest.approx(12.5)
    assert 0.0 <= out["low_ppl_sentence_ratio"] <= 1.0


def test_compute_perplexity_no_sentences(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prob, "_perplexity_of_ids", lambda ids, m, **kw: 9.0)
    out = prob.compute_perplexity("A", model=_FakeModel(), tokenizer=_FakeTokenizer())
    assert out["median_perplexity"] == 0.0
    assert out["perplexity_variance"] == 0.0


# --- binoculars ---------------------------------------------------------------


def test_binoculars_returns_positive_ratio() -> None:
    import torch

    class _BinoLoss:
        def __init__(self, v: float) -> None:
            self.v = v

        def __add__(self, other) -> _BinoLoss:
            return _BinoLoss(self.v + other.v)

        def __rmul__(self, scalar: float) -> _BinoLoss:
            return _BinoLoss(scalar * self.v)

    class _Out:
        def __init__(self, v: float) -> None:
            self.loss = torch.tensor(v)

    class _M:
        def __init__(self, loss_v: float) -> None:
            self._v = loss_v

        def parameters(self):
            yield torch.zeros(1)

        def __call__(self, input_ids, labels=None):
            return _Out(self._v)

    class _Tok:
        def __call__(self, text, **kw):
            return {"input_ids": torch.tensor([[1, 2, 3, 4, 5]])}

    score = bino_mod.compute_binoculars_score(
        "hello world test text",
        _M(1.0),
        _M(2.0),
        _Tok(),
        max_length=16,
    )
    assert score > 0


def test_load_binoculars_disabled_returns_none() -> None:
    assert bino_mod.load_binoculars_models("a", "b", enabled=False) is None


# --- pipeline wiring ----------------------------------------------------------


def _make_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ForensicsSettings:
    from forensics.config import get_settings

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[[authors]]
name = "Fixture Author"
slug = "fixture-author"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/fixture-author/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[probability]
reference_model = "stub-gpt2"
reference_model_revision = "abc123"
binoculars_enabled = false
max_sequence_length = 64
sliding_window_stride = 32
low_ppl_threshold = 15.0
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()
    settings = get_settings()
    return settings


def test_extract_probability_features_writes_parquet_and_model_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forensics.storage.repository import Repository, init_db

    settings = _make_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(pp, "get_project_root", lambda: tmp_path)

    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    repo = Repository(db_path)

    author = Author(
        id="author-1",
        name="Fixture Author",
        slug="fixture-author",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://www.mediaite.com/author/fixture-author/",
    )
    repo.upsert_author(author)

    text = (
        "The quick brown fox jumps over the lazy dog. "
        "This second sentence is a bit longer and contains additional words. "
        "Here we have a third piece of prose to round out the corpus. "
    ) * 5

    for i in range(3):
        repo.upsert_article(
            Article(
                id=f"art-{i}",
                author_id=author.id,
                url=f"https://www.mediaite.com/2024/01/0{i + 1}/post-{i}/",
                title=f"Post {i}",
                published_date=datetime(2024, 1, i + 1, tzinfo=UTC),
                clean_text=text,
                word_count=len(text.split()),
                content_hash=f"hash-{i}",
            )
        )

    monkeypatch.setattr(pp, "load_reference_model", lambda **kw: (_FakeModel(), _FakeTokenizer()))
    monkeypatch.setattr(pp, "load_binoculars_models", lambda *a, **kw: None)
    monkeypatch.setattr(prob, "_perplexity_of_ids", lambda ids, m, **kw: 18.0)

    count = pp.extract_probability_features(
        db_path, settings, author_slug="fixture-author", include_binoculars=False
    )
    assert count == 3

    card = json.loads((tmp_path / "data" / "probability" / "model_card.json").read_text())
    assert card["reference_model"] == "stub-gpt2"
    assert card["binoculars_enabled"] is False

    parquet_path = tmp_path / "data" / "probability" / "fixture-author.parquet"
    df = pl.read_parquet(parquet_path)
    assert df.height == 3
    expected_cols = {
        "article_id",
        "author_id",
        "publish_date",
        "mean_perplexity",
        "median_perplexity",
        "perplexity_variance",
        "min_sentence_ppl",
        "max_sentence_ppl",
        "ppl_skewness",
        "low_ppl_sentence_ratio",
        "binoculars_score",
    }
    assert expected_cols <= set(df.columns)


def test_extract_probability_features_unknown_author_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forensics.storage.repository import init_db

    settings = _make_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(pp, "get_project_root", lambda: tmp_path)
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)

    monkeypatch.setattr(pp, "load_reference_model", lambda **kw: (_FakeModel(), _FakeTokenizer()))

    with pytest.raises(ValueError, match="nope"):
        pp.extract_probability_features(
            db_path,
            settings,
            author_slug="nope",
            include_binoculars=False,
        )


# --- slow test (requires real torch model download) --------------------------


@pytest.mark.slow
def test_real_gpt2_perplexity_smoke() -> None:
    """Loads the real GPT-2 (~500MB) and scores a tiny snippet."""
    model, tok = prob.load_reference_model("gpt2", revision=None, device="cpu")
    try:
        out = prob.compute_perplexity(
            "The sun rose over the mountain and the village stirred to life.",
            model,
            tok,
            max_length=64,
            stride=32,
        )
        assert out["mean_perplexity"] > 0
    finally:
        prob.clear_model_cache()
