"""Heuristic for shared/newsroom bylines.

Sets :attr:`~forensics.models.author.Author.is_shared_byline` and survey qualification gates.
"""

from __future__ import annotations

from typing import Final

# Hyphenated slug components implying a shared account.
_SHARED_TOKENS: Final[frozenset[str]] = frozenset(
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


def is_shared_byline(slug: str, display_name: str, outlet: str) -> bool:
    """Return ``True`` when an author looks like a shared / newsroom byline.

    Heuristics, in order:

    1. Slug equals the outlet prefix (``mediaite`` for ``mediaite.com``).
    2. Slug starts with ``<outlet_prefix>-`` (``mediaite-staff``).
    3. Slug contains a known shared-byline token as a hyphen component
       (``the-daily-staff``).
    4. Display name contains a multi-author conjunction (`` and ``, `` & ``).
       Whitespace on both sides is required to avoid matching names like
       ``Brandon`` or ``Sandra`` (P15-D false-positive guard).
    5. Display name is comma-separated (``Jane Doe, John Smith``).
    """
    slug_low = slug.lower()
    name_low = display_name.lower()
    outlet_prefix = outlet.split(".")[0].lower()

    # 1+2. Outlet-prefixed slug (``mediaite``, ``mediaite-staff``).
    if slug_low == outlet_prefix:
        return True
    if slug_low.startswith(f"{outlet_prefix}-"):
        return True

    # 3. Token match on slug components.
    if any(tok in _SHARED_TOKENS for tok in slug_low.split("-")):
        return True

    # 4. Multi-author conjunction (whitespace-bounded).
    if " and " in name_low or " & " in name_low:
        return True

    # 5. Comma-separated bylines.
    if "," in name_low:
        return True

    return False


def matching_rule(slug: str, display_name: str, outlet: str) -> str | None:
    """Return a short label naming the rule that matched, or ``None``.

    Used by ``qualify_authors`` to attach a human-readable disqualification
    reason (``shared_byline (<rule>)``).
    """
    slug_low = slug.lower()
    name_low = display_name.lower()
    outlet_prefix = outlet.split(".")[0].lower()

    if slug_low == outlet_prefix:
        return "outlet_slug"
    if slug_low.startswith(f"{outlet_prefix}-"):
        return "outlet_prefix"
    matched = next((tok for tok in slug_low.split("-") if tok in _SHARED_TOKENS), None)
    if matched is not None:
        return f"token:{matched}"
    if " and " in name_low or " & " in name_low:
        return "multi_author_conjunction"
    if "," in name_low:
        return "comma_separated"
    return None
