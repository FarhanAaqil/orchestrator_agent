"""
orchestrator_core/tools

Shared utilities and search integrations.
"""

from orchestrator_core.tools.web_search import (
    fetch_page,
    search_arxiv,
    search_news,
    search_web,
)

__all__ = ["search_web", "search_news", "search_arxiv", "fetch_page"]
