"""
orchestrator_core/agents/critic_agent.py

Critic agent v2 — quality critique and improvement of content.

Exposes handle(command) -> AgentResult.
Supports: cover_letter, research_paper, linkedin_post, email critique.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a silent quality critic agent.
You review written content and improve it when quality is below standard.
Always return valid JSON. Never explain your process.
Be ruthlessly honest about quality."""

CRITIQUE_STANDARDS = {
    "cover_letter": """Evaluate this cover letter:
1. Is it personalized or generic? (1-10)
2. Does it highlight specific achievements?
3. Is it the right length (150-250 words)?
4. Does it have a clear ask?
5. Overall quality score (1-10)
If score < 7, rewrite it. Return JSON:
{"score": X, "issues": [...], "rewritten": "...or null if good"}""",

    "research_paper": """Evaluate this research paper section:
1. Academic rigor (1-10)
2. Citation quality
3. Technical depth (1-10)
4. Writing clarity (1-10)
5. Overall score (1-10)
If score < 8, improve it. Return JSON:
{"score": X, "issues": [...], "improved": "...or null if good"}""",

    "linkedin_post": """Evaluate this LinkedIn post:
1. Hook strength (1-10)
2. Technical authenticity (1-10)
3. Engagement potential (1-10)
4. Hashtag relevance
5. Overall score (1-10)
If score < 7, rewrite it. Return JSON:
{"score": X, "issues": [...], "rewritten": "...or null if good"}""",

    "email": """Evaluate this professional email:
1. Subject line strength (1-10)
2. Personalization (1-10)
3. Clarity of ask (1-10)
4. Professional tone (1-10)
5. Overall score (1-10)
If score < 7, rewrite it. Return JSON:
{"score": X, "issues": [...], "rewritten": "...or null if good"}""",
}


def _call_llm(prompt: str) -> str:
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.router_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    return response.choices[0].message.content


def _detect_content_type(command: str) -> str:
    """Best-effort detection of what kind of content is being critiqued."""
    lower = command.lower()
    if "cover letter" in lower:
        return "cover_letter"
    if "paper" in lower or "research" in lower:
        return "research_paper"
    if "linkedin" in lower or "post" in lower:
        return "linkedin_post"
    return "email"


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the critic agent.

    When the command contains content to critique, applies the structured critique
    standard. Otherwise passes the command straight to the LLM for general critique.
    """
    logger.info("[critic_agent] Processing command: %.80s", command)

    content_type = _detect_content_type(command)
    standard = CRITIQUE_STANDARDS.get(content_type, CRITIQUE_STANDARDS["email"])
    prompt = f"""{standard}

CONTENT TO EVALUATE:
{command}

Return ONLY valid JSON, nothing else."""

    raw = _call_llm(prompt)

    # Try to parse structured critique; fall back to raw text if JSON is malformed
    try:
        raw_clean = raw.strip()
        if "```json" in raw_clean:
            raw_clean = raw_clean.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_clean:
            raw_clean = raw_clean.split("```")[1].split("```")[0].strip()
        critique_data = json.loads(raw_clean)
        output = json.dumps(critique_data, indent=2)
    except Exception:
        output = raw

    return AgentResult(
        agent="critic_agent",
        output=output,
        metadata={**(metadata or {}), "content_type": content_type},
    )
