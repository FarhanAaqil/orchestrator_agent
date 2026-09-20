"""
tests/test_web_search.py

Tests for the multi-provider web search tool (Google CSE, SerpAPI, DuckDuckGo fallback, ArXiv).
"""

from unittest.mock import patch, MagicMock
import pytest

from orchestrator_core.tools.web_search import (
    search_web,
    search_news,
    search_arxiv,
    fetch_page,
    _search_google_custom,
    _search_serpapi,
    _search_ddg,
)
import utils.web_search as utils_web_search


def test_search_google_custom_provider(monkeypatch):
    """Google Custom Search should return structured results when keys are set."""
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "mock_key")
    monkeypatch.setenv("GOOGLE_SEARCH_CX", "mock_cx")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {"title": "Result 1", "snippet": "Snippet 1", "link": "https://example.com/1"},
            {"title": "Result 2", "snippet": "Snippet 2", "link": "https://example.com/2"},
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        res = _search_google_custom("multi-agent AI", max_results=2)
        assert res is not None
        assert len(res) == 2
        assert res[0]["title"] == "Result 1"
        assert res[0]["url"] == "https://example.com/1"


def test_search_serpapi_provider(monkeypatch):
    """SerpAPI should return structured results when key is set."""
    monkeypatch.setenv("SERPAPI_API_KEY", "mock_serpapi_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "organic_results": [
            {"title": "Serp Result 1", "snippet": "Serp Snippet 1", "link": "https://serp.com/1"}
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        res = _search_serpapi("deep learning", max_results=1)
        assert res is not None
        assert len(res) == 1
        assert res[0]["title"] == "Serp Result 1"
        assert res[0]["url"] == "https://serp.com/1"


def test_search_web_fallback_chain(monkeypatch):
    """search_web should fall back through providers and return results."""
    # Ensure Google and SerpAPI are not configured
    monkeypatch.delenv("GOOGLE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

    mock_ddg = [{"title": "DDG Title", "snippet": "DDG Snippet", "url": "https://ddg.com/1"}]
    with patch("orchestrator_core.tools.web_search._search_ddg", return_value=mock_ddg):
        results = search_web("autonomous agents", max_results=3)
        assert len(results) == 1
        assert results[0]["title"] == "DDG Title"


def test_utils_web_search_backward_compatibility():
    """utils.web_search functions should be identical to orchestrator_core.tools.web_search."""
    assert utils_web_search.search_web is search_web
    assert utils_web_search.search_news is search_news
    assert utils_web_search.search_arxiv is search_arxiv
    assert utils_web_search.fetch_page is fetch_page
