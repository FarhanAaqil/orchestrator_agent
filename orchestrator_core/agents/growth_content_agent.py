"""
orchestrator_core/agents/growth_content_agent.py

Growth/Content agent v2.

Key difference from v1: this agent NEVER calls publishing SDKs directly.
Any publish action goes through request_approval() — the SDK import and
execution live exclusively in orchestrator_core/core/approval_gate.py.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

AAQIL_BIO = """
Farhan Aaqil — Final year B.Tech AI/ML student at JPNCE Mahbubnagar.
Building LLM agents, LangChain pipelines, and AI systems.
Published researcher. Intern at Jala Academy.
GitHub: github.com/FarhanAaqil
""".strip()

_SYSTEM_PROMPT = f"""You are Aaqil's Growth and Content Agent.
You create engaging tech content about Aaqil's projects and journey.
Bio: {AAQIL_BIO}
Always write in first person as Aaqil. Be authentic, technical but accessible.
Avoid hustle culture clichés. Be real, share learnings, show the code."""


def _call_llm(prompt: str) -> str:
    settings = get_settings()
    try:
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.router_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=750,
        )
        return response.choices[0].message.content
    except Exception as exc:
        err_msg = str(exc).lower()
        if "api_key" in err_msg or "401" in err_msg or "unauthorized" in err_msg or "invalid api key" in err_msg:
            logger.warning("[growth_agent] Groq auth error: %s — providing structured demo output.", exc)
            return (
                "⚠️ *Notice: Configured GROQ_API_KEY in .env is expired/invalid. Showing simulated content:*\n\n"
                "## Building Production Multi-Agent Systems: Why Unbypassable Gates Matter\n\n"
                "By Farhan Aaqil\n\n"
                "When deploying multi-agent frameworks in enterprise environments, standard LLM tool calling has a fatal flaw: "
                "payload substitution at execution time. If an agent hallucinates or an unauthorized caller passes parameters directly to an execution endpoint, safety gates are rendered meaningless.\n\n"
                "### The Solution: Zero-Parameter CAS Execution\n\n"
                "In Orchestrator v2, we solved this with atomic Compare-And-Set (CAS) concurrency on SQLite:\n\n"
                "```python\n"
                "# Caller passes ONLY the approval ID — zero payload allowed at execution time\n"
                "execute_approved(approval_id, db)\n"
                "```\n\n"
                "This guarantees that the exact payload reviewed and approved by a human is what gets executed by isolated SDK handlers — zero leakage, zero substitution."
            )
        raise


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the growth/content agent.

    Content generation always returns text. When the user asks to publish,
    the agent signals it via action_type so the caller can queue an approval.
    The agent NEVER imports or calls Hashnode/Dev.to SDKs directly.
    """
    logger.info("[growth_content_agent] Processing command: %.80s", command)

    lower = command.lower()
    output = _call_llm(command)

    # Detect publish intent — signal for approval gate, never call SDK here
    action_type: Optional[str] = None
    if "publish" in lower and "hashnode" in lower:
        action_type = "publish_hashnode"
        logger.info("Publish intent detected — queuing for approval gate")
    elif "publish" in lower and ("devto" in lower or "dev.to" in lower):
        action_type = "publish_devto"
        logger.info("Publish intent detected — queuing for approval gate")

    return AgentResult(
        agent="growth_content_agent",
        output=output,
        action_type=action_type,
        metadata=metadata or {},
    )
