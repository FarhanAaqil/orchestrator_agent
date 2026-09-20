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
import logging
import re
import hashlib
import time
from typing import Union

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.core.circuit_breaker import CircuitBreaker
from orchestrator_core.models import RouterResult, ClarificationNeeded

logger = logging.getLogger(__name__)

# Module-level breaker — shared across all classify() calls in the process.
# 3 consecutive Groq failures → OPEN for 30 s.
_groq_breaker = CircuitBreaker(service="groq_router", failure_threshold=3, cooldown_seconds=30.0)

# In-memory LRU/TTL cache for repeated router classifications
_classification_cache: dict[str, tuple[float, Union[RouterResult, ClarificationNeeded]]] = {}
ROUTER_CACHE_TTL = 300.0  # 5 minutes
ROUTER_CACHE_MAX_ENTRIES = 512


def clear_router_cache() -> None:
    """Clear the in-memory router classification cache."""
    _classification_cache.clear()

SUPPORTED_AGENTS = {
    "career_agent": "Resume tailoring, skill gaps, interview prep, career roadmaps, cover letters.",
    "research_agent": "Academic paper writing, journal search, research summaries, ArXiv paper analysis.",
    "growth_content_agent": "Technical blog posts, Dev.to/Hashnode publishing, devlogs, technical writing, Twitter threads.",
    "critic_agent": "Quality critique and improvement of cover letters, posts, papers, emails, and code.",
    "info_agent": "System architecture, how agents/pipelines/approvals work, Farhan Aaqil's projects portfolio, and documentation.",
    "email_agent": "Checking email inbox, reading unread messages, drafting recruiter outreach, and sending emails.",
    "github_agent": "GitHub repositories, user profiles, commit history, README generation, commit messages, creating issues or PR comments.",
    "linkedin_agent": "LinkedIn networking, recruiter discovery, 300-character connection notes, cold DMs, headline/profile optimization, and LinkedIn posts.",
    "general_chat_agent": "Casual conversation, general brainstorming, high-level technical advice, chitchat, greetings, and Toji companion.",
}

_ROUTER_SYSTEM_PROMPT = """\
You are a precise router for a multi-agent AI assistant system.
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


def _heuristic_classify(command: str) -> dict:
    """Deterministic heuristic fallback when Groq API key is invalid or unavailable."""
    lower = command.lower().strip()

    # Ambiguous commands
    if any(k in lower for k in ("what should i do", "what next", "help me decide", "which one")):
        return {
            "agent": "career_agent",
            "confidence": 0.45,
            "reasoning": "Ambiguous input — requires user clarification between career and growth pathways.",
        }

    # Email agent keywords
    if any(k in lower for k in ("email", "inbox", "gmail", "mail", "send mail", "send email", "unread emails", "check inbox")):
        return {
            "agent": "email_agent",
            "confidence": 0.95,
            "reasoning": "Detected email, inbox, or outreach intent from keywords.",
        }

    # GitHub agent keywords
    if any(k in lower for k in ("github", "repo", "repos", "repository", "git commit", "pull request", "open issue", "github issue")):
        return {
            "agent": "github_agent",
            "confidence": 0.95,
            "reasoning": "Detected GitHub repository or development workflow intent from keywords.",
        }

    # LinkedIn agent keywords
    if any(k in lower for k in ("linkedin", "connection note", "connect note", "recruiter", "cold dm", "inmail", "networking note")):
        return {
            "agent": "linkedin_agent",
            "confidence": 0.95,
            "reasoning": "Detected LinkedIn networking or recruiter search intent from keywords.",
        }

    # Career keywords
    if any(k in lower for k in ("resume", "cv", "job", "cover letter", "cover-letter", "interview", "career", "skill", "internship", "application")):
        return {
            "agent": "career_agent",
            "confidence": 0.95,
            "reasoning": "Detected resume/career intent from keywords.",
        }

    # Research keywords
    if any(k in lower for k in ("paper", "arxiv", "academic", "research", "journal", "literature", "predatory", "cite", "citation")):
        return {
            "agent": "research_agent",
            "confidence": 0.95,
            "reasoning": "Detected academic research intent from keywords.",
        }

    # Growth keywords
    if any(k in lower for k in ("blog", "dev.to", "devto", "hashnode", "post", "tweet", "twitter", "thread", "devlog", "content")):
        return {
            "agent": "growth_content_agent",
            "confidence": 0.95,
            "reasoning": "Detected technical writing/growth intent from keywords.",
        }

    # Critic keywords
    if any(k in lower for k in ("critique", "score", "review", "feedback", "grade", "evaluate", "rate")):
        return {
            "agent": "critic_agent",
            "confidence": 0.92,
            "reasoning": "Detected evaluation/critique intent from keywords.",
        }

    # Info / portfolio / system documentation keywords
    if any(k in lower for k in ("farhan aaqil", "portfolio", "projects", "architecture", "how does", "how do", "how it works", "working", "about the system", "system doc")):
        return {
            "agent": "info_agent",
            "confidence": 0.95,
            "reasoning": "Detected system documentation or project portfolio inquiry.",
        }

    # General chat / greetings keywords
    if any(k in lower for k in ("hi", "hello", "hey", "who are you", "what can you do", "toji", "jarvis", "help me", "how are you", "good morning", "good evening", "chat")):
        return {
            "agent": "general_chat_agent",
            "confidence": 0.95,
            "reasoning": "Detected conversational greeting or general assistant query.",
        }

    # Default fallback to general chat agent for conversational queries
    return {
        "agent": "general_chat_agent",
        "confidence": 0.75,
        "reasoning": "General query routed to general chat assistant.",
    }


def _call_groq(command: str) -> dict:
    """Make the raw Groq API call. Wrapped by circuit breaker externally."""
    settings = get_settings()
    try:
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
    except Exception as exc:
        err_msg = str(exc).lower()
        if "api_key" in err_msg or "401" in err_msg or "unauthorized" in err_msg or "invalid api key" in err_msg:
            logger.warning("[router] Groq API key is invalid/expired (%s) — using heuristic routing.", exc)
            return _heuristic_classify(command)
        raise


def get_circuit_status() -> dict:
    """Return circuit breaker diagnostic metrics."""
    return {
        "service": _groq_breaker.service,
        "state": _groq_breaker.state,
        "consecutive_failures": _groq_breaker._consecutive_failures,
        "failure_threshold": _groq_breaker.failure_threshold,
    }


def reset_circuit_breaker() -> None:
    """Manually reset router circuit breaker to CLOSED."""
    _groq_breaker.reset()



def prompt_hash(command: str) -> str:
    """Return a short hash of the system prompt + command for staleness tracking."""
    payload = _build_system_prompt() + command
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def classify(command: str, use_cache: bool = True) -> Union[RouterResult, ClarificationNeeded]:
    """
    Classify a user command and return either a RouterResult or a ClarificationNeeded.

    Goes through the circuit breaker — raises CircuitOpenError if the breaker
    is OPEN (i.e., Groq has been failing repeatedly).
    Uses server-side in-memory caching to eliminate redundant LLM calls.
    """
    cache_key = command.strip().lower()
    if use_cache and cache_key in _classification_cache:
        cached_time, cached_result = _classification_cache[cache_key]
        if time.monotonic() - cached_time < ROUTER_CACHE_TTL:
            logger.debug("[router] Cache hit for command: %s", command[:40])
            return cached_result

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

        result = ClarificationNeeded(
            candidates=candidates[:3],
            reasoning=reasoning or f"Confidence {confidence:.0%} is below the {threshold:.0%} threshold.",
        )
    else:
        result = RouterResult(agent=agent, confidence=confidence, reasoning=reasoning)

    if use_cache:
        if len(_classification_cache) >= ROUTER_CACHE_MAX_ENTRIES:
            oldest_keys = sorted(_classification_cache, key=lambda k: _classification_cache[k][0])[:100]
            for k in oldest_keys:
                _classification_cache.pop(k, None)
        _classification_cache[cache_key] = (time.monotonic(), result)

    return result
