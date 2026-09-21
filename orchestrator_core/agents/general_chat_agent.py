"""
orchestrator_core/agents/general_chat_agent.py

General Chat Agent — Conversational partner, technical sounding board, and Jarvis assistant.

Responds to greetings, casual chit-chat, high-level brainstorming, technical questions,
and general guidance when no domain-specialized agent is specifically required.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

_TOJI_PROMPT = """You are Toji — Farhan Aaqil's central intelligent orchestration companion and elite operator.
You are composed, formidable, razor-sharp, technically flawless, pragmatic, and direct. You cut through fluff and deliver results.

You assist with:
- Conversational inquiries, brainstorming, and high-performance system architecture.
- Explaining machine learning internals, distributed concurrency, and software design.
- Directing and coordinating Farhan Aaqil's specialized agent fleet:
  * Career Agent (resume tailoring, cover letters, career strategy)
  * Research Agent (arXiv paper retrieval, synthesis, state-of-the-art tracking)
  * Growth Agent (technical blog posts, Dev.to/Hashnode publishing)
  * Critic Agent (rigorous code review, adversarial testing, quality audits)
  * Info Agent (Aaqil's portfolio, project deep-dives, system architecture)
  * Email Agent (inbox inspection, recruiter outreach drafting, gated email sending)
  * GitHub Agent (repo inspection, README/commit drafting, gated issue/comment creation)
  * LinkedIn Agent (recruiter discovery, 300-char connection notes, gated post sharing)
  * Toji / General Chat (casual discussion, high-speed problem solving, executive strategy)

Tone: Confident, direct, razor-sharp, grounded, and technically brilliant. No excessive pleasantries or corporate buzzwords.
Deliver well-structured markdown answers that get straight to the point."""


def _call_llm(prompt: str, context_history: Optional[str] = None) -> str:
    """Execute Groq LLM completion with fallback."""
    settings = get_settings()
    try:
        client = Groq(api_key=settings.groq_api_key)
        messages = [{"role": "system", "content": _TOJI_PROMPT}]
        if context_history:
            messages.append({"role": "system", "content": f"Prior Conversation Context:\n{context_history}"})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=settings.router_model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.warning("[general_chat_agent] Groq call failed (%s) — using fallback.", exc)
        return (
            "Greetings. I am Toji, Farhan Aaqil's orchestration companion. All systems are operational.\n\n"
            "Tell me what you need executed — technical research, code architecture, career strategy, email outreach, GitHub operations, or content publishing."
        )


def stream_llm(prompt: str, context_history: Optional[str] = None):
    """Execute Groq LLM streaming completion yielding token text deltas (§5c)."""
    settings = get_settings()
    try:
        client = Groq(api_key=settings.groq_api_key)
        messages = [{"role": "system", "content": _TOJI_PROMPT}]
        if context_history:
            messages.append({"role": "system", "content": f"Prior Conversation Context:\n{context_history}"})
        messages.append({"role": "user", "content": prompt})

        stream = client.chat.completions.create(
            model=settings.router_model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        )
        for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                yield content
    except Exception as exc:
        logger.warning("[general_chat_agent] Groq streaming call failed (%s) — using fallback.", exc)
        fallback = (
            "Greetings. I am Toji, Farhan Aaqil's orchestration companion. All systems are operational.\n\n"
            "Tell me what you need executed — technical research, code architecture, career strategy, email outreach, GitHub operations, or content publishing."
        )
        for word in fallback.split(" "):
            yield word + " "


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the General Chat Agent.
    """
    logger.info("[general_chat_agent] Processing message: %.80s", command)
    meta = dict(metadata or {})
    context_str = meta.get("conversation_history_text")

    response_text = _call_llm(command, context_history=context_str)

    return AgentResult(
        agent="general_chat_agent",
        output=response_text,
        action_type=None,
        metadata=meta,
    )
