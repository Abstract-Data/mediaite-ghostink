"""T-03 — curated pre-2020-style journalism stays below AI marker frequency ceiling."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from forensics.features.lexical import extract_lexical_features

pytest.importorskip("spacy")


def _nlp():
    import spacy

    try:
        return spacy.load("en_core_web_md")
    except OSError:
        pytest.skip("en_core_web_md not installed (uv run python -m spacy download en_core_web_md)")


# Short synthetic clips in a wire-service register (no deliberate AI-disclosure phrasing).
_PRE_2020_JOURNALISM_SNIPPETS: tuple[str, ...] = (
    "The mayor announced a bond measure after the council voted twelve to three "
    "Thursday night. Opposition leaders said the plan would strain the sewer budget.",
    "Forecasters expect snow above six thousand feet by Sunday. Travelers on I-70 "
    "should carry chains, state patrol said.",
    "Union representatives and plant management met for a fourth session without "
    "a wage agreement. Workers authorized a strike if talks stall next week.",
    "The appellate panel upheld the district court on procedural grounds and did "
    "not reach the First Amendment question.",
    "Crop reports showed corn futures down two cents on higher expected yields "
    "across the upper Midwest.",
)


@pytest.mark.parametrize("snippet", _PRE_2020_JOURNALISM_SNIPPETS)
def test_curated_pre2020_snippets_have_low_ai_marker_rate(snippet: str) -> None:
    nlp = _nlp()
    doc = nlp(snippet)
    rate = extract_lexical_features(snippet, doc)["ai_marker_frequency"]
    assert rate < 0.75, f"unexpectedly high marker rate={rate!r} for snippet"


@settings(max_examples=25, deadline=None)
@given(
    idx=st.integers(min_value=0, max_value=len(_PRE_2020_JOURNALISM_SNIPPETS) - 1),
    noise=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        max_size=48,
    ),
)
def test_pre2020_snippet_plus_ascii_noise_stays_below_marker_ceiling(
    idx: int,
    noise: str,
) -> None:
    nlp = _nlp()
    base = _PRE_2020_JOURNALISM_SNIPPETS[idx]
    text = f"{base} {noise}".strip()
    doc = nlp(text)
    rate = extract_lexical_features(text, doc)["ai_marker_frequency"]
    assert rate < 1.5, f"marker rate {rate} exceeded ceiling for augmented pre-2020 text"
