"""Shared httpx.AsyncClient construction for scrapers."""

from __future__ import annotations

import httpx

from forensics.config.settings import ScrapingConfig

DEFAULT_TIMEOUT = 30.0


def client_headers(scraping: ScrapingConfig) -> dict[str, str]:
    return {"User-Agent": scraping.user_agent}


def create_scraping_client(scraping: ScrapingConfig) -> httpx.AsyncClient:
    """Async HTTP client with consistent timeout, redirects, and User-Agent."""
    return httpx.AsyncClient(
        headers=client_headers(scraping),
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )
