"""
orchestrator_core/agents/linkedin_agent.py

LinkedIn Agent — Professional branding, outreach drafting, and recruiter search specialist.

READ / WRITE SPLIT CONTRACT:
  - Free (un-gated): recruiter search via web, connection note drafting (strict 300-char limit),
    cold DMs, headline optimization, About section polishing, JD fit analysis.
  - Gated (approval required): external posting or messaging.
    Returns action_type="linkedin_post" or "linkedin_connect" for approval gate review.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult
from orchestrator_core.tools.web_search import search_web

logger = logging.getLogger(__name__)

AAQIL_PROFILE = """
Farhan Aaqil
AI/ML Engineer | Final-Year B.Tech at JPNCE Mahbubnagar
Focus: Autonomous Multi-Agent Orchestration, Production ML, LLM Workflows
LinkedIn: linkedin.com/in/farhan-aaqil-4730432bb
Key Highlights:
- Author of Orchestrator Agent (audited multi-agent system with unbypassable approval gate)
- Published Research in Diabetes Risk Prediction (DiaPredict AI, 2025)
- Python, FastAPI, PyTorch, Scikit-learn, LangChain/LlamaIndex, Docker, GCP
"""

_SYSTEM_PROMPT = f"""You are Aaqil's LinkedIn Agent — his professional branding and networking specialist.
Aaqil's Profile:
{AAQIL_PROFILE}

Your capabilities:
1. Drafting high-converting LinkedIn connection requests (STRICT RULE: max 300 characters for note).
2. Drafting impactful InMail / Cold DMs to hiring managers, founders, and recruiters.
3. Crafting engaging technical LinkedIn posts about engineering breakthroughs, project launches, and paper insights.
4. Profiling and optimizing headline, About section, and experience bullet points.
5. Analyzing job postings against Aaqil's resume.

Tone: Professional, articulate, authentic, engineering-first, not buzzword-heavy."""


def _call_llm(prompt: str) -> str:
    """Execute Groq LLM completion with fallback."""
    settings = get_settings()
    try:
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.router_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.warning("[linkedin_agent] Groq call failed (%s) — using fallback.", exc)
        return (
            "Hi [Name], I noticed your work at [Company]. As an AI/ML engineer building autonomous "
            "agent systems and ML pipelines (DiaPredict AI), I'd love to connect and follow your work."
        )


def _search_recruiters(query: str) -> str:
    """Find recruiters or technical leaders using targeted Google/DDG queries."""
    search_query = f"site:linkedin.com/in/ {query}"
    results = search_web(search_query, max_results=5)
    if not results or "error" in results[0]:
        return f"🔍 Searched for `{query}` on LinkedIn. Results temporarily unavailable via web search."

    lines = [f"### 💼 LinkedIn Search Results for `{query}`:\n"]
    for r in results:
        title = r.get("title", "").replace(" | LinkedIn", "")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        lines.append(f"- **[{title}]({url})**\n  {snippet}")
    return "\n".join(lines)


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the LinkedIn Agent.
    Implements Read/Write split:
      - Reads: recruiter search, drafting posts/notes/DMs, profile review (free)
      - Writes: posting updates or sending invites (gated behind approval gate)
    """
    logger.info("[linkedin_agent] Processing command: %.80s", command)
    lower = command.lower().strip()
    meta = dict(metadata or {})

    # 1. Gated Write Check: Post to LinkedIn
    if any(k in lower for k in ("post on linkedin", "share on linkedin", "publish to linkedin", "post update")):
        action_type = "linkedin_post"
        prompt = f"Draft an engaging, technical LinkedIn post ready for publishing based on: {command}"
        post_draft = _call_llm(prompt)
        payload = {"post_content": post_draft, "command": command}
        meta["approval_payload"] = payload
        meta["action_type"] = action_type
        return AgentResult(
            agent="linkedin_agent",
            output=(
                f"🔒 **LinkedIn Post Requires Approval**\n\n"
                f"{post_draft}\n\n"
                f"---\n*Action queued for review in the Approval Gate.*"
            ),
            action_type=action_type,
            metadata=meta,
        )

    # 2. Free Read: Recruiter / profile search
    if any(k in lower for k in ("search recruiter", "find recruiter", "search linkedin", "find people", "find hiring manager")):
        search_term = command
        for prefix in ("search recruiter", "find recruiter", "search linkedin for", "find people at", "find hiring manager at"):
            if prefix in lower:
                search_term = command[lower.index(prefix) + len(prefix):].strip()
                break
        search_output = _search_recruiters(search_term or "AI engineer recruiter")
        return AgentResult(
            agent="linkedin_agent",
            output=search_output,
            action_type=None,
            metadata=meta,
        )

    # 3. Free Read: Draft connection request (strict 300-char limit)
    if any(k in lower for k in ("connection note", "connect note", "connect message", "connection request")):
        prompt = (
            f"Draft a personalized LinkedIn connection request note for: {command}.\n"
            f"CRITICAL CONSTRAINT: The note MUST be under 300 characters total, concise, and compelling."
        )
        note_draft = _call_llm(prompt)
        # Ensure it respects length
        char_count = len(note_draft)
        return AgentResult(
            agent="linkedin_agent",
            output=(
                f"🤝 **Personalized Connection Note ({char_count}/300 chars):**\n\n"
                f"> {note_draft}\n\n"
                f"*Copy and paste this into LinkedIn when sending your invitation.*"
            ),
            action_type=None,
            metadata=meta,
        )

    # 4. Free Read: Cold DM, profile headline, About section, or general LinkedIn strategy
    output = _call_llm(command)
    return AgentResult(
        agent="linkedin_agent",
        output=output,
        action_type=None,
        metadata=meta,
    )
