"""Tests for perplexity / Binoculars / probability pipeline (Phase 9)."""

from __future__ import annotations

import json
import math
import types
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
import torch

from forensics.config import get_settings


def test_perplexity_computation(monkeypatch: pytest.MonkeyPatch) -> None:
    from forensics.features import probability as prob_mod

    def fake_nll(*_a, **_k):
        return 1.0

    def fake_sents(*_a, **_k):
        return [10.0, 12.0]

    monkeypatch.setattr(prob_mod, "_token_sequence_nll", fake_nll)
    monkeypatch.setattr(prob_mod, "sentence_perplexities", fake_sents)
    model = object()
    tok = object()
    out = prob_mod.compute_perplexity(
        "Hello world. Second sentence here.",
        model,
        tok,
        max_length=64,
        stride=32,
        low_ppl_threshold=100.0,
        device="cpu",
    )
    assert out["mean_perplexity"] == pytest.approx(2.718281828, rel=1e-5)
    assert out["median_perplexity"] == pytest.approx(11.0)
    assert out["min_sentence_ppl"] == 10.0
    assert out["max_sentence_ppl"] == 12.0


def test_perplexity_ai_vs_human(monkeypatch: pytest.MonkeyPatch) -> None:
    from forensics.features import probability as prob_mod

    def make_ppl(article_nll: float, sents: list[float]):
        def _nll(*_a, **_k):
            return article_nll

        def _sents(*_a, **_k):
            return sents

        return _nll, _sents

    nll_ai, sents_ai = make_ppl(0.5, [5.0, 5.5])
    nll_human, sents_human = make_ppl(3.0, [80.0, 120.0])
    model = object()
    tok = object()

    monkeypatch.setattr(prob_mod, "_token_sequence_nll", nll_ai)
    monkeypatch.setattr(prob_mod, "sentence_perplexities", sents_ai)
    ai = prob_mod.compute_perplexity("ai-like", model, tok, device="cpu")
    monkeypatch.setattr(prob_mod, "_token_sequence_nll", nll_human)
    monkeypatch.setattr(prob_mod, "sentence_perplexities", sents_human)
    human = prob_mod.compute_perplexity("human-like", model, tok, device="cpu")
    assert ai["mean_perplexity"] < human["mean_perplexity"]


def test_burstiness_uniform_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from forensics.features import probability as prob_mod

    monkeypatch.setattr(prob_mod, "_token_sequence_nll", lambda *_a, **_k: 1.0)
    monkeypatch.setattr(prob_mod, "sentence_perplexities", lambda *_a, **_k: [7.0, 7.0, 7.0])
    out = prob_mod.compute_perplexity("Same. Same. Same.", object(), object(), device="cpu")
    assert out["perplexity_variance"] == pytest.approx(0.0, abs=1e-9)


def test_burstiness_diverse_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from forensics.features import probability as prob_mod

    monkeypatch.setattr(prob_mod, "_token_sequence_nll", lambda *_a, **_k: 2.0)
    monkeypatch.setattr(
        prob_mod,
        "sentence_perplexities",
        lambda *_a, **_k: [5.0, 200.0, 40.0],
    )
    long_mid = "Short. " + "Long " * 80 + " Mid."
    out = prob_mod.compute_perplexity(long_mid, object(), object(), device="cpu")
    assert out["perplexity_variance"] > 10.0


def test_sliding_window(monkeypatch: pytest.MonkeyPatch) -> None:
    from forensics.features import probability as prob_mod

    class StubModel:
        config = types.SimpleNamespace(n_positions=256)

        def __call__(self, chunk, labels=None):
            class LMOut:
                loss = torch.tensor(0.7)

            return LMOut()

    tok = MagicMock()
    tok.return_value = {"input_ids": torch.ones(1, 600, dtype=torch.long)}
    out = prob_mod.compute_perplexity(
        "word " * 200,
        StubModel(),
        tok,
        max_length=128,
        stride=64,
        device="cpu",
    )
    assert out["mean_perplexity"] > 1.0
    assert not math.isnan(out["mean_perplexity"])


@pytest.mark.slow
def test_perplexity_tiny_gpt2() -> None:
    pytest.importorskip("torch")
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from forensics.features.probability import compute_perplexity

    name = "hf-internal-testing/tiny-random-gpt2"
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name)
    model.eval()
    text = "The quick brown fox jumps over the lazy dog. " * 3
    out = compute_perplexity(text, model, tok, max_length=64, stride=32, device="cpu")
    assert out["mean_perplexity"] > 0
    assert out["mean_perplexity"] < 1e9


def test_binoculars_score_range(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    from forensics.features import binoculars as binoc_mod

    base, inst = object(), object()

    def fake_sliding(model, input_ids, max_length, stride, device):
        if model is base:
            return (100.0, 50)
        return (50.0, 50)

    monkeypatch.setattr(
        "forensics.features.probability._sliding_window_mean_nll",
        fake_sliding,
    )
    tok = MagicMock()
    tok.return_value = {"input_ids": torch.ones(1, 40, dtype=torch.long)}
    score = binoc_mod.compute_binoculars_score(
        "hello world " * 5,
        base,
        inst,
        tok,
        max_length=32,
        device=torch.device("cpu"),
    )
    # sum_b/n_b = 2, sum_i/n_i = 1 -> ppl_b = e^2, ppl_i = e^1 -> ratio = e
    assert score == pytest.approx(2.718281828, rel=1e-4)


def test_model_card_creation(tmp_path: Path, forensics_config_path: Path) -> None:
    from forensics.features.probability_pipeline import _write_model_card

    get_settings.cache_clear()
    settings = get_settings()
    card = tmp_path / "model_card.json"
    _write_model_card(settings, card, device_used="cpu")
    assert card.is_file()
    data = json.loads(card.read_text(encoding="utf-8"))
    assert data["reference_model"] == settings.probability.reference_model
    assert data["reference_model_revision"] == settings.probability.reference_model_revision
    assert data["device_used"] == "cpu"
    assert "scored_at" in data
    get_settings.cache_clear()


def test_model_version_mismatch(
    tmp_path: Path, forensics_config_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from forensics.features.probability_pipeline import _model_card_matches_disk

    get_settings.cache_clear()
    settings = get_settings()
    card = tmp_path / "model_card.json"
    card.write_text(
        json.dumps(
            {
                "reference_model": "gpt2",
                "reference_model_revision": "wrong-rev",
                "binoculars_base": settings.probability.binoculars_model_base,
                "binoculars_instruct": settings.probability.binoculars_model_instruct,
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        ok = _model_card_matches_disk(settings, card)
    assert ok is False
    assert "model_card.json" in caplog.text
    get_settings.cache_clear()


def test_cpu_fallback(forensics_config_path: Path) -> None:
    pytest.importorskip("torch")
    from forensics.features.binoculars import load_binoculars_models

    get_settings.cache_clear()
    settings = get_settings()
    import torch

    out = load_binoculars_models(settings.probability, device=torch.device("cpu"))
    assert out is None
    get_settings.cache_clear()


def test_parquet_schema(tmp_path: Path) -> None:
    rows = [
        {
            "article_id": "a1",
            "author_id": "auth1",
            "publish_date": "2024-01-02",
            "mean_perplexity": 10.0,
            "median_perplexity": 9.0,
            "perplexity_variance": 2.0,
            "min_sentence_ppl": 5.0,
            "max_sentence_ppl": 20.0,
            "ppl_skewness": 0.1,
            "low_ppl_sentence_ratio": 0.2,
            "binoculars_score": None,
        }
    ]
    path = tmp_path / "fixture-author.parquet"
    pl.DataFrame(rows).write_parquet(path)
    df = pl.read_parquet(path)
    for col in (
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
    ):
        assert col in df.columns


def test_probability_stack_available() -> None:
    from forensics.features.probability_pipeline import probability_stack_available

    assert isinstance(probability_stack_available(), bool)
