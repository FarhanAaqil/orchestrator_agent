"""
orchestrator_core/tools/read package

Read-only, idempotent tools (Capability.READ).
Guaranteed zero direct real-world side effects.
"""

from orchestrator_core.tools.read.arxiv_search import arxiv_search, fetch_arxiv_text
from orchestrator_core.tools.read.ddg_search import ddg_news_search, ddg_search
from orchestrator_core.tools.read.email_read import email_read
from orchestrator_core.tools.read.fetch_page import fetch_page
from orchestrator_core.tools.read.github_read import github_read
from orchestrator_core.tools.read.google_search import google_search
from orchestrator_core.tools.read.shared_client import safe_get, safe_head

__all__ = [
    "arxiv_search",
    "fetch_arxiv_text",
    "ddg_search",
    "ddg_news_search",
    "email_read",
    "fetch_page",
    "github_read",
    "google_search",
    "safe_get",
    "safe_head",
]
