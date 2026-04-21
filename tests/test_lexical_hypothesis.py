"""Property-based checks for lexical feature bounds (P3-TEST-002)."""

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
