"""
orchestrator_core/tools/web_search.py

Multi-provider search engine integration.
Fallback chain:
  1. Google Custom Search JSON API (if GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX set)
  2. SerpAPI (if SERPAPI_API_KEY set)
  3. DuckDuckGo (ddgs / duckduckgo_search fallback)
"""

from __future__ import annotations

from io import BytesIO
import logging
import os
from typing import Any, Optional
import urllib.parse

import requests

logger = logging.getLogger(__name__)


def _search_google_custom(query: str, max_results: int = 5) -> Optional[list[dict[str, str]]]:
    """Search via Google Custom Search JSON API."""
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or os.getenv("GOOGLE_API_KEY")
    cx = os.getenv("GOOGLE_SEARCH_CX") or os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cx:
        return None

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(max(1, max_results), 10),
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            return [
                {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", ""),
                }
                for item in items
            ]
        logger.warning("[web_search] Google CSE returned HTTP %d: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("[web_search] Google CSE error: %s", exc)
    return None


def _search_serpapi(query: str, max_results: int = 5) -> Optional[list[dict[str, str]]]:
    """Search via SerpAPI."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return None

    try:
        url = "https://serpapi.com/search.json"
        params = {
            "q": query,
            "api_key": api_key,
            "num": min(max(1, max_results), 10),
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            organic = data.get("organic_results", [])
            return [
                {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", ""),
                }
                for item in organic[:max_results]
            ]
        logger.warning("[web_search] SerpAPI returned HTTP %d: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("[web_search] SerpAPI error: %s", exc)
    return None


def _search_ddg(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Fallback search via DuckDuckGo."""
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
        return results
    except Exception as exc:
        logger.warning("[web_search] DuckDuckGo search error: %s", exc)
        return [{"error": str(exc), "query": query}]


def search_web(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Search the web using available providers in priority order:
    Google Custom Search -> SerpAPI -> DuckDuckGo
    """
    # 1. Google Custom Search
    google_res = _search_google_custom(query, max_results=max_results)
    if google_res is not None and len(google_res) > 0:
        return google_res

    # 2. SerpAPI
    serp_res = _search_serpapi(query, max_results=max_results)
    if serp_res is not None and len(serp_res) > 0:
        return serp_res

    # 3. DuckDuckGo
    return _search_ddg(query, max_results=max_results)


def search_news(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search news using DuckDuckGo news."""
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
        return results
    except Exception as exc:
        logger.warning("[web_search] News search error: %s", exc)
        return [{"error": str(exc), "query": query}]


def search_arxiv(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search arXiv preprint papers."""
    try:
        import arxiv

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        results = []
        for paper in client.results(search):
            results.append({
                "title": paper.title,
                "authors": [a.name for a in paper.authors[:4]],
                "abstract": paper.summary[:400],
                "url": paper.pdf_url,
                "arxiv_id": paper.entry_id,
                "published": str(paper.published)[:10],
                "categories": paper.categories[:3],
            })
        return results
    except Exception as exc:
        logger.warning("[web_search] arXiv search error: %s", exc)
        return [{"error": str(exc), "query": query}]


def fetch_page(url: str) -> str:
    """Fetch web page content text."""
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        return resp.text[:3000]
    except Exception as exc:
        return f"Error: {exc}"


def fetch_arxiv_full_text(pdf_url: str) -> str:
    """Download and extract first 10 pages of arXiv PDF text."""
    try:
        import pypdf

        if not pdf_url.endswith(".pdf"):
            pdf_url = pdf_url.replace("abs", "pdf") + ".pdf"

        resp = requests.get(
            pdf_url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        if resp.status_code == 200:
            reader = pypdf.PdfReader(BytesIO(resp.content))
            text = ""
            for i in range(min(10, len(reader.pages))):
                text += reader.pages[i].extract_text() + "\n"
            return text
        return f"Error: HTTP {resp.status_code}"
    except Exception as exc:
        return f"Error extracting text: {exc}"
