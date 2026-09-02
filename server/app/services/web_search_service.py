"""Best-effort web search for skill nodes, with graceful degradation.

Provider chain: Tavily (if ``TAVILY_API_KEY`` is set) → DuckDuckGo (``ddgs``)
→ unavailable. Every failure degrades silently — callers must treat an
empty result list as "no web evidence" and fall back to model knowledge.

Search budget lives with the caller (plan skill caps total queries per
generation); this module only caps results per query.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT_SECONDS = 12
_COOLDOWN_SECONDS = 300

_last_failure_at: float = 0.0


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


def _tavily_search(query: str, max_results: int) -> list[WebSearchResult]:
    import os

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not configured")

    response = requests.post(
        _TAVILY_URL,
        json={"api_key": api_key, "query": query, "max_results": max_results},
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return [
        WebSearchResult(
            title=str(item.get("title", "")),
            url=str(item.get("url", "")),
            snippet=str(item.get("content", "")),
        )
        for item in payload.get("results", [])
        if item.get("url")
    ]


def _duckduckgo_search(query: str, max_results: int) -> list[WebSearchResult]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        raw = ddgs.text(query, max_results=max_results)
    return [
        WebSearchResult(
            title=str(item.get("title", "")),
            url=str(item.get("href", "")),
            snippet=str(item.get("body", "")),
        )
        for item in raw
        if item.get("href")
    ]


def web_search_available() -> bool:
    """True when a provider is configured/importable and not cooling down."""
    if time.monotonic() - _last_failure_at < _COOLDOWN_SECONDS:
        return False
    import os

    if os.getenv("TAVILY_API_KEY", "").strip():
        return True
    try:
        import ddgs  # noqa: F401

        return True
    except ImportError:
        return False


def search_web(query: str, max_results: int = 5) -> list[WebSearchResult]:
    """Search the web; empty list means "no evidence" (never raises)."""
    global _last_failure_at

    if not query.strip():
        return []

    providers = [_tavily_search, _duckduckgo_search]
    for provider in providers:
        try:
            results = provider(query, max_results)
            if results:
                return results
        except Exception as exc:
            logger.info("web search provider %s failed: %s", provider.__name__, exc)

    _last_failure_at = time.monotonic()
    return []


def cross_validate_links(results: list[WebSearchResult]) -> dict[str, list[str]]:
    """Group result URLs by registered domain for cross-source validation."""
    by_domain: dict[str, list[str]] = {}
    for result in results:
        domain = urlparse(result.url).netloc.lower().removeprefix("www.")
        if domain:
            by_domain.setdefault(domain, []).append(result.url)
    return by_domain
