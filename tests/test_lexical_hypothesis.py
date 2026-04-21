"""Property-based checks for lexical feature invariants (P3-TEST-002)."""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from forensics.features import lexical


def _fake_doc(words: list[str]) -> object:
    """Minimal stand-in for spaCy Doc: iterable of tokens with ``is_alpha`` and ``text``."""

    class _Tok:
        __slots__ = ("text", "is_alpha")

        def __init__(self, text: str, is_alpha: bool) -> None:
            self.text = text
            self.is_alpha = is_alpha

    class _Doc:
        __slots__ = ("_tokens",)

        def __init__(self, tokens: list[_Tok]) -> None:
            self._tokens = tokens

        def __iter__(self):
            return iter(self._tokens)

        @property
        def sents(self):
            class _Sent:
                def __init__(self, inner: list[_Tok]) -> None:
                    self._inner = inner

                def __iter__(self):
                    return iter(self._inner)

            return [_Sent(self._tokens)]

    toks = [_Tok(w, w.isalpha()) for w in words]
    return _Doc(toks)


_ALPHA_WORD = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=1,
    max_size=12,
)


@settings(max_examples=80)
@given(
    words=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "M", "N")),
            min_size=1,
            max_size=12,
        ),
        min_size=5,
        max_size=80,
    ),
)
def test_lexical_ratios_bounds(words: list[str]) -> None:
    text = " ".join(words)
    doc = _fake_doc(words)
    out = lexical.extract_lexical_features(text, doc)  # type: ignore[arg-type]
    ttr = float(out["ttr"])
    mattr = float(out["mattr"])
    hapax = float(out["hapax_ratio"])
    yk = float(out["yules_k"])
    if math.isfinite(ttr):
        assert 0.0 <= ttr <= 1.0
    if math.isfinite(mattr):
        assert 0.0 <= mattr <= 1.0
    if math.isfinite(hapax):
        assert 0.0 <= hapax <= 1.0
    if math.isfinite(yk):
        assert yk >= 0.0


@settings(max_examples=40)
@given(words=st.lists(_ALPHA_WORD, min_size=5, max_size=40, unique=True))
def test_ttr_equals_one_when_all_unique(words: list[str]) -> None:
    """TTR == 1 when every alpha token is unique."""
    text = " ".join(words)
    doc = _fake_doc(words)
    out = lexical.extract_lexical_features(text, doc)  # type: ignore[arg-type]
    assert float(out["ttr"]) == 1.0
    # Every word is a hapax (appears exactly once), so hapax_ratio should be 1.
    assert float(out["hapax_ratio"]) == 1.0


@settings(max_examples=40)
@given(words=st.lists(_ALPHA_WORD, min_size=3, max_size=20, unique=True))
def test_hapax_zero_when_every_word_repeats(words: list[str]) -> None:
    """No word appears exactly once → hapax_ratio == 0."""
    doubled = list(words) + list(words)
    text = " ".join(doubled)
    doc = _fake_doc(doubled)
    out = lexical.extract_lexical_features(text, doc)  # type: ignore[arg-type]
    assert float(out["hapax_ratio"]) == 0.0


@settings(max_examples=40)
@given(words=st.lists(_ALPHA_WORD, min_size=5, max_size=30, unique=True))
def test_ttr_non_increasing_under_duplication(words: list[str]) -> None:
    """Duplicating the token stream cannot increase TTR (more tokens, same vocab)."""
    text_once = " ".join(words)
    doc_once = _fake_doc(words)
    out_once = lexical.extract_lexical_features(text_once, doc_once)  # type: ignore[arg-type]

    doubled = list(words) + list(words)
    text_twice = " ".join(doubled)
    doc_twice = _fake_doc(doubled)
    out_twice = lexical.extract_lexical_features(text_twice, doc_twice)  # type: ignore[arg-type]

    assert float(out_twice["ttr"]) <= float(out_once["ttr"]) + 1e-9
