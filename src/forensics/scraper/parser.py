"""HTML parsing utilities (Phase 3+)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from forensics.utils.text import clean_text as normalize_article_text

logger = logging.getLogger(__name__)

_REMOVE_CLASS_SUBSTRINGS = (
    "related-posts",
    "social-share",
    "advertisement",
    "sidebar",
    "newsletter",
    "comments",
    "jp-relatedposts",
)


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

    for tag in container.find_all(["script", "style", "nav", "aside", "footer"]):
        tag.decompose()

    for el in container.find_all(True):
        classes = " ".join(el.get("class") or []).lower()
        if any(s in classes for s in _REMOVE_CLASS_SUBSTRINGS):
            el.decompose()

    raw_text = container.get_text(separator="\n")
    return normalize_article_text(raw_text)


def extract_article_text_from_rest(content_rendered: str) -> str:
    """Extract body text from WP REST ``content.rendered`` (already body-scoped HTML)."""
    if not content_rendered:
        return ""
    soup = BeautifulSoup(content_rendered, "lxml")
    for tag in soup.find_all(["script", "style", "nav", "aside", "footer"]):
        tag.decompose()
    for el in soup.find_all(True):
        classes = " ".join(el.get("class") or []).lower()
        if any(s in classes for s in _REMOVE_CLASS_SUBSTRINGS):
            el.decompose()
    return normalize_article_text(soup.get_text(separator="\n"))


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


def extract_metadata(html: str) -> dict[str, Any]:
    """Extract supplemental metadata (Open Graph, article tags, schema.org)."""
    soup = BeautifulSoup(html, "lxml")
    meta: dict[str, Any] = {}

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

    for blob in _ld_json_blobs(soup):
        typ = blob.get("@type")
        types = typ if isinstance(typ, list) else ([typ] if typ else [])
        if "NewsArticle" in types or "Article" in types:
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

    return meta


_COAUTHOR_DELIMITERS: tuple[str, ...] = (" and ", " & ", " with ", ", ")


def looks_coauthored(author_text: str) -> bool:
    """Heuristic: multiple bylines use ``and``, ``&``, ``with``, or comma-separated names."""
    t = author_text.strip()
    if not t:
        return False
    low = t.lower()
    return any(sep in low for sep in _COAUTHOR_DELIMITERS)
