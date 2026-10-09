"""
orchestrator_core/tools/registry.py

Central capability-governed Tool Registry (Section 5.5).
Enforces:
  1. Registry Gate: Only Capability.READ and Capability.PROPOSE tools can be registered.
     Capability.EXEC tools are prohibited from the agent registry.
  2. Agent Allowlist Filtering: for_agent(name) returns only tools within that agent's
     specific authorized tool set.
  3. JSON Schema generation for LLM tool calling.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from orchestrator_core.tools.propose.propose_action import ProposeActionArgs, propose_action
from orchestrator_core.tools.read.arxiv_search import ArxivSearchArgs, arxiv_search
from orchestrator_core.tools.read.ddg_search import DDGSearchArgs, ddg_search
from orchestrator_core.tools.read.email_read import EmailReadArgs, email_read
from orchestrator_core.tools.read.fetch_page import FetchPageArgs, fetch_page
from orchestrator_core.tools.read.github_read import GitHubReadArgs, github_read
from orchestrator_core.tools.read.google_search import GoogleSearchArgs, google_search
from orchestrator_core.tools.spec import Capability, ToolSpec

logger = logging.getLogger(__name__)

# Standard authorized tool allowlists per agent
AGENT_TOOL_ALLOWLISTS: dict[str, frozenset[str]] = {
    # Research: academic papers, web search, page reading
    "research_agent": frozenset({"google_search", "fetch_page", "arxiv_search", "ddg_search"}),
    # Career: job board reads, portfolio github inspect, company search
    "career_agent": frozenset({"fetch_page", "github_read", "google_search"}),
    # Growth & Content: research trends, fetch docs, propose publication
    "growth_content_agent": frozenset({"google_search", "fetch_page", "propose_action"}),
    # Critic: pure reasoning over artifacts; zero network tools
    "critic_agent": frozenset(),
    # GitHub: read repositories and issues; propose issue creation and comments
    "github_agent": frozenset({"github_read", "propose_action"}),
    # Email: read unread inbox correspondence; propose outbound emails
    "email_agent": frozenset({"email_read", "propose_action"}),
    # LinkedIn: search public profiles, fetch articles, propose LinkedIn posts
    "linkedin_agent": frozenset({"ddg_search", "fetch_page", "propose_action"}),
    # Info: system documentation and reference lookups
    "info_agent": frozenset({"google_search", "fetch_page", "ddg_search"}),
    # General Chat: casual search
    "general_chat_agent": frozenset({"ddg_search"}),
    # Master orchestrator agent: full autonomous research, search, and proposal coordination
    "orchestrator": frozenset({"google_search", "fetch_page", "arxiv_search", "ddg_search", "github_read", "email_read", "propose_action"}),
}

# Alias map for short agent names
_AGENT_ALIASES: dict[str, str] = {
    "research": "research_agent",
    "career": "career_agent",
    "growth": "growth_content_agent",
    "growth_content": "growth_content_agent",
    "critic": "critic_agent",
    "github": "github_agent",
    "email": "email_agent",
    "linkedin": "linkedin_agent",
    "info": "info_agent",
    "general_chat": "general_chat_agent",
    "general": "general_chat_agent",
}


def _canonical_agent_name(name: str) -> str:
    cleaned = name.strip().lower()
    return _AGENT_ALIASES.get(cleaned, cleaned)


class ToolRegistry:
    """
    Registry managing tool specifications and agent-specific capability allowlists.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """
        Register a tool specification.
        Fails if capability is EXEC to prevent execution leakage into agent contexts.
        """
        if spec.capability == Capability.EXEC:
            raise ValueError(
                f"Security violation: tool '{spec.name}' has Capability.EXEC. "
                "Execution tools must NEVER be registered in the agent registry."
            )
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        """Fetch tool spec by name."""
        return self._tools.get(name)

    def all_specs(self) -> dict[str, ToolSpec]:
        """Return all registered specifications."""
        return dict(self._tools)

    def for_agent(self, agent_name: str) -> dict[str, ToolSpec]:
        """
        Return the dictionary of ToolSpecs authorized for the given agent.
        Guarantees:
          - Only returns tools in the agent's explicit allowlist.
          - Only returns tools with Capability.READ or Capability.PROPOSE.
          - Zero Capability.EXEC tools.
        """
        canonical = _canonical_agent_name(agent_name)
        allowed_names = AGENT_TOOL_ALLOWLISTS.get(canonical, frozenset())

        authorized: dict[str, ToolSpec] = {}
        for name in allowed_names:
            tool = self._tools.get(name)
            if tool is not None:
                if tool.capability in (Capability.READ, Capability.PROPOSE):
                    authorized[name] = tool
                else:
                    logger.critical(
                        "Illegal capability %s found for tool %s while resolving for %s",
                        tool.capability, name, agent_name,
                    )
        return authorized

    def schemas_for_agent(self, agent_name: str) -> list[dict[str, Any]]:
        """
        Generate OpenAI-compatible tool definitions for LLM function calling.
        """
        tools = self.for_agent(agent_name)
        schemas = []
        for spec in tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.schema.model_json_schema(),
                },
            })
        return schemas


def create_default_registry() -> ToolRegistry:
    """Factory creating and populating the standard system tool registry."""
    reg = ToolRegistry()

    # 1. Google Search
    reg.register(
        ToolSpec(
            name="google_search",
            capability=Capability.READ,
            description="Search the web using Google Custom Search with 24h cache and DDG fallback.",
            func=google_search,
            schema=GoogleSearchArgs,
            timeout_s=15.0,
            cacheable=True,
            egress_allowlist=("googleapis.com", "duckduckgo.com"),
        )
    )

    # 2. Fetch Webpage
    reg.register(
        ToolSpec(
            name="fetch_page",
            capability=Capability.READ,
            description="Safely fetch and extract human-readable text from an HTTP/HTTPS webpage.",
            func=fetch_page,
            schema=FetchPageArgs,
            timeout_s=15.0,
            cacheable=False,
        )
    )

    # 3. ArXiv Search
    reg.register(
        ToolSpec(
            name="arxiv_search",
            capability=Capability.READ,
            description="Search academic papers and scientific pre-prints on arXiv.",
            func=arxiv_search,
            schema=ArxivSearchArgs,
            timeout_s=15.0,
            cacheable=True,
            egress_allowlist=("arxiv.org", "export.arxiv.org"),
        )
    )

    # 4. DuckDuckGo Search
    reg.register(
        ToolSpec(
            name="ddg_search",
            capability=Capability.READ,
            description="Perform free web searches via DuckDuckGo.",
            func=ddg_search,
            schema=DDGSearchArgs,
            timeout_s=15.0,
            cacheable=True,
            egress_allowlist=("duckduckgo.com",),
        )
    )

    # 5. GitHub Read
    reg.register(
        ToolSpec(
            name="github_read",
            capability=Capability.READ,
            description="Inspect GitHub repositories, users, issues, and commits in read-only mode.",
            func=github_read,
            schema=GitHubReadArgs,
            timeout_s=15.0,
            cacheable=True,
            egress_allowlist=("api.github.com", "github.com"),
        )
    )

    # 6. Email Read
    reg.register(
        ToolSpec(
            name="email_read",
            capability=Capability.READ,
            description="Read unread email correspondence and check inbox status.",
            func=email_read,
            schema=EmailReadArgs,
            timeout_s=15.0,
            cacheable=False,
        )
    )

    # 7. Propose Action
    reg.register(
        ToolSpec(
            name="propose_action",
            capability=Capability.PROPOSE,
            description="Queue an external real-world action (send email, publish post, create issue) for human approval.",
            func=propose_action,
            schema=ProposeActionArgs,
            timeout_s=10.0,
            cacheable=False,
        )
    )

    return reg


# Singleton default registry instance
default_registry = create_default_registry()
