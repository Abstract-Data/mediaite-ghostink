"""T-03 — curated pre-2020-style journalism stays below AI marker frequency ceiling."""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
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

_EXTRA_NEUTRAL_SNIPPETS: tuple[str, ...] = (
    "The harbor master delayed sailings after gale warnings went up at dawn.",
    "County auditors flagged overtime spending in the roads department last quarter.",
    "Hospital officials said flu admissions rose modestly but beds remained available.",
    "The transit agency will replace aging railcars starting next fiscal year.",
    "School board members debated start times but took no final vote Tuesday.",
    "Fire crews contained the brush fire within two hours, officials reported.",
    "The university raised tuition by three percent for in-state undergraduates.",
    "Police closed two lanes after a tanker truck spilled diesel near mile marker fourteen.",
    "Voters will decide a parks bond in November after petitions cleared verification.",
    "The orchestra extended its season by two weeks following strong ticket sales.",
    "City planners released draft zoning maps for the riverfront redevelopment area.",
    "State regulators approved the merger with conditions on retail pricing.",
    "The library will extend weekend hours after volunteers staffed a pilot program.",
    "Airport contractors finished resurfacing the secondary runway ahead of schedule.",
    "Marine biologists tagged juvenile salmon to study migration timing this spring.",
    "The museum loaned twelve portraits to a regional tour opening in April.",
    "County sheriffs urged boaters to wear life jackets during the holiday weekend.",
    "Utility crews restored power overnight after storms downed lines east of town.",
    "The housing authority opened a lottery for fifty subsidized downtown units.",
    "Farmers markets will accept SNAP tokens at every booth starting Saturday.",
    "Coast Guard crews practiced hoist rescues off the headlands in heavy fog.",
    "The film festival sold out its documentary block within ninety minutes online.",
    "Meteorologists tracked a tropical wave but said formation odds remained low.",
    "The wildlife refuge closed a trail while biologists monitored nesting raptors.",
    "City arborists will inspect century-old elms along the boulevard this month.",
    "The port authority signed a lease for cold storage near the container terminal.",
    "Regional rail tickets will rise five percent unless the legislature intervenes.",
    "The clinic expanded evening hours for pediatric vaccinations through winter.",
    "Archaeologists cataloged pottery shards before winter rains reach the dig site.",
    "The symphony hired a guest conductor for the contemporary works concert series.",
)

_ALL_CURATED_SNIPPETS: tuple[str, ...] = _PRE_2020_JOURNALISM_SNIPPETS + _EXTRA_NEUTRAL_SNIPPETS


@pytest.mark.parametrize("snippet", _ALL_CURATED_SNIPPETS)
def test_curated_pre2020_snippets_have_low_ai_marker_rate(snippet: str) -> None:
    nlp = _nlp()
    doc = nlp(snippet)
    rate = extract_lexical_features(snippet, doc)["ai_marker_frequency"]
    assert rate < 0.75, f"unexpectedly high marker rate={rate!r} for snippet"


_wordish = st.text(
    alphabet=st.characters(whitelist_categories=("L", "M", "N", "P", "Z", "S")),
    min_size=2,
    max_size=9,
)


@settings(max_examples=35, deadline=None)
@given(
    base=st.sampled_from(_ALL_CURATED_SNIPPETS),
    extra_words=st.lists(_wordish, min_size=0, max_size=12).map(
        lambda parts: " ".join(parts).strip()
    ),
)
def test_curated_base_plus_generated_words_stays_below_marker_ceiling(
    base: str,
    extra_words: str,
) -> None:
    nlp = _nlp()
    text = f"{base} {extra_words}".strip()
    assume(len(text.split()) >= 12)
    doc = nlp(text)
    rate = extract_lexical_features(text, doc)["ai_marker_frequency"]
    assert rate < 1.5, f"marker rate {rate} exceeded ceiling for augmented pre-2020 text"
