"""
orchestrator_core/tools package

Capability-governed tool system with strict READ / PROPOSE / EXEC boundaries.
"""

from orchestrator_core.tools.propose import ProposeActionArgs, propose_action
from orchestrator_core.tools.read import (
    arxiv_search,
    ddg_news_search,
    ddg_search,
    email_read,
    fetch_arxiv_text,
    fetch_page,
    github_read,
    google_search,
    safe_get,
    safe_head,
)
from orchestrator_core.tools.registry import (
    AGENT_TOOL_ALLOWLISTS,
    ToolRegistry,
    create_default_registry,
    default_registry,
)
from orchestrator_core.tools.spec import Capability, ToolSpec

# Backward-compatibility aliases
search_web = google_search
search_news = ddg_news_search
search_arxiv = arxiv_search

__all__ = [
    "Capability",
    "ToolSpec",
    "ToolRegistry",
    "default_registry",
    "create_default_registry",
    "AGENT_TOOL_ALLOWLISTS",
    "google_search",
    "fetch_page",
    "arxiv_search",
    "fetch_arxiv_text",
    "ddg_search",
    "ddg_news_search",
    "github_read",
    "email_read",
    "propose_action",
    "ProposeActionArgs",
    "safe_get",
    "safe_head",
    "search_web",
    "search_news",
    "search_arxiv",
]
