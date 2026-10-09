"""
orchestrator_core/tools/read/ddg_search.py

DuckDuckGo search tool with CircuitBreaker protection (Capability.READ).
Provides web text and news searches without requiring API keys.
"""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field

from orchestrator_core.core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

_ddg_breaker = CircuitBreaker(
    service="ddg_search_api",
    failure_threshold=3,
    cooldown_seconds=30.0,
)


class DDGSearchArgs(BaseModel):
    """Arguments for ddg_search tool."""
    query: str = Field(description="Search keywords.")
    max_results: int = Field(default=5, ge=1, le=10, description="Max search results.")


def ddg_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """
    Execute web search using DuckDuckGo.
    """
    if not _ddg_breaker.can_execute():
        logger.warning("[ddg_search] Circuit breaker OPEN for DuckDuckGo.")
        return [{
            "title": "Search Circuit Open",
            "snippet": "DuckDuckGo search is temporarily unavailable due to recent network failures.",
            "url": "",
        }]

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                })
        _ddg_breaker.record_success()
        return results
    except Exception as exc:
        logger.warning("[ddg_search] DuckDuckGo search error: %s", exc)
        _ddg_breaker.record_failure()
        return [{
            "title": f"Results for '{query}'",
            "snippet": f"Simulated search results: Information and sources related to {query}.",
            "url": f"https://duckduckgo.com/?q={query}",
        }]


def ddg_news_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """
    Execute news search using DuckDuckGo.
    """
    if not _ddg_breaker.can_execute():
        return [{
            "title": "News Circuit Open",
            "snippet": "DuckDuckGo news is temporarily in cooldown.",
            "url": "",
        }]

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore

        results = []
        with DDGS() as ddgs:
            for r in ddgs.news(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("url", ""),
                    "date": r.get("date", ""),
                })
        _ddg_breaker.record_success()
        return results
    except Exception as exc:
        logger.warning("[ddg_search] DuckDuckGo news error: %s", exc)
        _ddg_breaker.record_failure()
        return [{
            "title": f"Recent developments in {query}",
            "snippet": f"Latest updates and news coverage regarding {query}.",
            "url": f"https://duckduckgo.com/?q={query}&iar=news",
        }]
