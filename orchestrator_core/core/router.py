"""
orchestrator_core/core/router.py

LLM-based command router.

classify(command) -> RouterResult | ClarificationNeeded

All Groq calls go through the module-level CircuitBreaker so that repeated
LLM failures fail-fast instead of stacking timeout threads.
Confidence threshold is read lazily from settings — no global state on import.
"""

from __future__ import annotations

import json
import re
import hashlib
from typing import Union

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.core.circuit_breaker import CircuitBreaker
from orchestrator_core.models import RouterResult, ClarificationNeeded

# Module-level breaker — shared across all classify() calls in the process.
# 3 consecutive Groq failures → OPEN for 30 s.
_groq_breaker = CircuitBreaker(service="groq_router", failure_threshold=3, cooldown_seconds=30.0)

SUPPORTED_AGENTS = {
    "career_agent": "Resume tailoring, skill gaps, interview prep, career roadmaps, cover letters.",
    "research_agent": "Academic paper writing, journal search, research summaries, ArXiv paper analysis.",
    "growth_content_agent": "LinkedIn posts, Twitter threads, blog posts, devlogs, content calendars.",
    "critic_agent": "Quality critique and improvement of cover letters, posts, papers, emails.",
}

_ROUTER_SYSTEM_PROMPT = """\
You are a precise router for a 4-agent AI assistant system.
Your job is to classify user commands to exactly one agent and return a confidence score.

Available agents:
{agent_list}

Return a JSON object with this exact shape:
{{
  "agent": "<agent_name>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>"
}}

Rules:
- agent must be one of the agent names above — no other values.
- confidence must be a float between 0.0 and 1.0.
- If the command is ambiguous between two agents, set confidence below 0.6.
- reasoning must be a concise explanation (under 20 words).
- Never add extra keys. Return ONLY the JSON object.
""".strip()


def _build_system_prompt() -> str:
    agent_list = "\n".join(f"- {k}: {v}" for k, v in SUPPORTED_AGENTS.items())
    return _ROUTER_SYSTEM_PROMPT.format(agent_list=agent_list)


def _call_groq(command: str) -> dict:
    """Make the raw Groq API call. Wrapped by circuit breaker externally."""
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.router_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": command},
        ],
        temperature=0.0,
        max_tokens=200,
    )
    raw = response.choices[0].message.content
    # Strip any markdown fences the model might add despite JSON mode
    if "```" in raw:
        match = re.search(r"```(?:json)?(.*?)```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()
    return json.loads(raw)


def prompt_hash(command: str) -> str:
    """Return a short hash of the system prompt + command for staleness tracking."""
    payload = _build_system_prompt() + command
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def classify(command: str) -> Union[RouterResult, ClarificationNeeded]:
    """
    Classify a user command and return either a RouterResult or a ClarificationNeeded.

    Goes through the circuit breaker — raises CircuitOpenError if the breaker
    is OPEN (i.e., Groq has been failing repeatedly).
    """
    settings = get_settings()
    threshold = settings.router_confidence_threshold

    data = _groq_breaker.call(_call_groq, command)

    agent = data.get("agent", "").strip()
    confidence = float(data.get("confidence", 0.0))
    reasoning = data.get("reasoning", "")

    if agent not in SUPPORTED_AGENTS or confidence < threshold:
        # Determine candidate list: always include the returned agent if valid
        candidates = list(SUPPORTED_AGENTS.keys()) if agent not in SUPPORTED_AGENTS else [agent]
        # Add the second-most-likely agent if model returned a valid one
        if agent in SUPPORTED_AGENTS and len(candidates) == 1:
            # Expand candidates to the full list minus the returned one so caller
            # can surface them as alternatives
            candidates = [agent] + [a for a in SUPPORTED_AGENTS if a != agent]

        return ClarificationNeeded(
            candidates=candidates[:3],
            reasoning=reasoning or f"Confidence {confidence:.0%} is below the {threshold:.0%} threshold.",
        )

    return RouterResult(agent=agent, confidence=confidence, reasoning=reasoning)
