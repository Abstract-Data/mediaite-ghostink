"""Text normalization helpers."""

from __future__ import annotations

import html
import re
import unicodedata


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_text(raw: str) -> str:
    """Strip HTML entities, normalize unicode, and collapse whitespace."""
    unescaped = html.unescape(raw)
    normalized = unicodedata.normalize("NFKC", unescaped)
    return normalize_whitespace(normalized)


def word_count(text: str) -> int:
    if not text.strip():
        return 0
    return len(text.split())
