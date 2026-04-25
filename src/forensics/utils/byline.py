"""Conservative byline classification helpers."""

from __future__ import annotations

__all__ = ["shared_byline_reason"]

_SHARED_TOKENS: frozenset[str] = frozenset(
    {
        "staff",
        "editors",
        "newsroom",
        "team",
        "desk",
        "contributor",
        "contributors",
        "bureau",
        "wire",
    }
)


def shared_byline_reason(slug: str, display_name: str, outlet: str) -> str | None:
    """Return the matched shared-byline rule, or ``None`` for individual bylines."""
    slug_low = slug.lower().strip()
    name_low = display_name.lower().strip()
    outlet_prefix = outlet.split(".")[0].lower().strip()
    slug_tokens = frozenset(token for token in slug_low.split("-") if token)

    if slug_low == outlet_prefix:
        return "outlet_slug"
    if slug_low.startswith(f"{outlet_prefix}-"):
        return "outlet_prefixed_slug"
    matched_tokens = sorted(slug_tokens & _SHARED_TOKENS)
    if matched_tokens:
        return f"shared_token:{matched_tokens[0]}"
    if " and " in name_low or " & " in name_low:
        return "multi_author_name"
    if "," in name_low:
        return "comma_separated_name"
    return None
