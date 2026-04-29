"""HTML parsing utilities for scraped article bodies and metadata."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from forensics.utils.text import clean_text as normalize_article_text
from forensics.utils.text import word_count

logger = logging.getLogger(__name__)


def filter_insufficient_article_body(clean_text: str, *, log_label: str) -> str:
    """Return body text for persistence, or empty string with a logged audit trail.

    Whitespace-only and zero-word bodies are cleared so downstream simhash dedup
    does not collapse unrelated empties onto identical fingerprints.
    """
    if not clean_text.strip():
        logger.warning("%s: empty article body after extract (whitespace-only)", log_label)
        return ""
    wc = word_count(clean_text)
    if wc == 0:
        logger.warning("%s: zero word count after extract", log_label)
        return ""
    return clean_text


_REMOVE_CLASS_SUBSTRINGS = (
    "related-posts",
    "social-share",
    "advertisement",
    "sidebar",
    "newsletter",
    "comments",
    "jp-relatedposts",
)


def _sanitize_and_extract(root: BeautifulSoup | Tag) -> str:
    """Strip boilerplate tags/classes, then normalize body text."""
    for tag in root.find_all(["script", "style", "nav", "aside", "footer"]):
        tag.decompose()
    for el in root.find_all(True):
        classes = " ".join(el.get("class") or []).lower()
        if any(s in classes for s in _REMOVE_CLASS_SUBSTRINGS):
            el.decompose()
    return normalize_article_text(root.get_text(separator="\n"))


def _strip_stray_angle_brackets(text: str) -> str:
    """Remove stray/unpaired angle brackets from malformed markup fragments.

    Only removes isolated brackets that don't appear to be part of valid markup
    or legitimate prose (e.g., comparison operators, quoted technical text).
    Preserves brackets that are part of tag-like patterns.
    """
    # Remove isolated < or > that appear:
    # - At word boundaries with surrounding whitespace/punctuation
    # - Not part of tag patterns like <word> or </word>
    # This preserves legitimate uses like "x < y" or quoted tech syntax
    text = re.sub(r"(?<![<>\w])<(?![<>/\w])", "", text)  # Isolated <
    text = re.sub(r"(?<![<>/\w])>(?![<>\w])", "", text)  # Isolated >
    return text


def extract_article_text(html: str) -> str:
    """Pull main article body text from Mediaite / WordPress HTML."""
    soup = BeautifulSoup(html, "lxml")
    container = (
        soup.find("div", class_="entry-content")
        or soup.find("article")
        or soup.find("div", class_="post-content")
    )
    if container is None:
        logger.warning("extract_article_text: no content container found")
        return ""
    return _sanitize_and_extract(container)


def extract_article_text_from_rest(content_rendered: str) -> str:
    """Extract body text from WP REST ``content.rendered`` (already body-scoped HTML)."""
    if not content_rendered:
        return ""
    soup = BeautifulSoup(content_rendered, "lxml")
    return _strip_stray_angle_brackets(_sanitize_and_extract(soup))


def _meta_content(soup: BeautifulSoup, *, prop: str | None = None, name: str | None = None) -> str:
    if prop:
        tag = soup.find("meta", attrs={"property": prop})
    else:
        tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return ""


def _ld_json_blobs(soup: BeautifulSoup) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    out.append(item)
    return out


def _apply_open_graph_meta(soup: BeautifulSoup, meta: dict[str, Any]) -> None:
    section = _meta_content(soup, prop="og:section") or _meta_content(soup, name="section")
    if section:
        meta["og_section"] = section

    tags: list[str] = []
    for m in soup.find_all("meta", attrs={"property": "article:tag"}):
        c = m.get("content")
        if c:
            tags.append(str(c).strip())
    if tags:
        meta["article_tags"] = tags

    author_meta = _meta_content(soup, prop="article:author") or _meta_content(
        soup, prop="og:author"
    )
    if author_meta:
        meta["page_author"] = author_meta


def _merge_ld_json_news_article(blob: dict[str, Any], meta: dict[str, Any]) -> None:
    typ = blob.get("@type")
    types = typ if isinstance(typ, list) else ([typ] if typ else [])
    if "NewsArticle" not in types and "Article" not in types:
        return
    if blob.get("author"):
        meta.setdefault("schema_author", blob.get("author"))
    if blob.get("datePublished"):
        meta.setdefault("schema_date_published", blob.get("datePublished"))
    article_section = blob.get("articleSection")
    if article_section and "og_section" not in meta:
        meta["og_section"] = str(article_section)
    keywords = blob.get("keywords")
    if isinstance(keywords, str) and "article_tags" not in meta:
        parts = [k.strip() for k in re.split(r"[,;]", keywords) if k.strip()]
        if parts:
            meta["article_tags"] = parts


def extract_metadata(html: str) -> dict[str, Any]:
    """Extract supplemental metadata (Open Graph, article tags, schema.org)."""
    soup = BeautifulSoup(html, "lxml")
    meta: dict[str, Any] = {}
    _apply_open_graph_meta(soup, meta)
    for blob in _ld_json_blobs(soup):
        _merge_ld_json_news_article(blob, meta)
    return meta


# Unambiguous co-author delimiters — direct substring match is safe.
_COAUTHOR_WORDS: tuple[str, ...] = (" and ", " & ", " with ")

# Name suffixes / credentials that should be ignored when deciding whether a
# comma-separated byline represents multiple authors (e.g., "John Smith, Jr.").
_SUFFIX_TOKENS: frozenset[str] = frozenset(
    {
        "jr",
        "jr.",
        "sr",
        "sr.",
        "ii",
        "iii",
        "iv",
        "esq",
        "esq.",
        "phd",
        "md",
    },
)


def looks_coauthored(author_text: str) -> bool:
    """Heuristic: detect multi-author bylines.

    Matches the unambiguous cases (``and`` / ``&`` / ``with``). Comma is
    ambiguous between ``"Last, First"`` and ``"Name1, Name2"``; only count
    commas when each side looks like a multi-word name (at least ``First
    Last``) and isn't a suffix/credential token like ``Jr.`` or ``PhD``.
    """
    t = author_text.strip()
    if not t:
        return False
    low = t.lower()
    if any(sep in low for sep in _COAUTHOR_WORDS):
        return True
    if "," not in t:
        return False
    parts = [p.strip() for p in t.split(",")]
    name_parts = [p for p in parts if p and p.lower().rstrip(".") not in _SUFFIX_TOKENS]
    return len(name_parts) >= 2 and all(" " in p for p in name_parts)
