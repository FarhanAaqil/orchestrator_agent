"""
utils/web_search.py

Backward-compatible re-export module pointing to orchestrator_core.tools.web_search.
"""

from orchestrator_core.tools.web_search import (
    fetch_arxiv_full_text,
    fetch_page,
    search_arxiv,
    search_news,
    search_web,
)

__all__ = [
    "search_web",
    "search_news",
    "search_arxiv",
    "fetch_page",
    "fetch_arxiv_full_text",
]
