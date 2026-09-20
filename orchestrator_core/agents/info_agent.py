"""
orchestrator_core/agents/info_agent.py

System documentation, project knowledge, and conversational assistance agent.
Answers questions about Farhan Aaqil's projects, orchestrator architecture,
agent workflows, system operation, and general conversational queries.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

AAQIL_PORTFOLIO = """
Author Profile: Farhan Aaqil
Degree: B.Tech in Artificial Intelligence & Machine Learning (AIML), JPNCE Mahbubnagar (2027)
Email: fadurrani543@gmail.com | Phone: +91-6300825009
GitHub: github.com/FarhanAaqil | LinkedIn: linkedin.com/in/farhan-aaqil-4730432bb
Experience: Python Full Stack Developer & AIML Intern at Jala Academy

Featured Projects:
1. Orchestrator Agent:
   - High-throughput multi-agent orchestration engine built on FastAPI & SQLite.
   - Core Features: LLM router with confidence calibration, fail-fast circuit breaker (Groq),
     unbypassable human-in-the-loop approval gate with atomic CAS concurrency (zero payload substitution),
     and step-by-step pipeline audit logger.
   - Active Agents: Career Agent, Research Agent, Growth Agent, Critic Agent, Info Agent.
   - Pipelines: Apply workflow, Publish workflow, Research workflow.

2. DiaPredict AI (Published Research, 2025):
   - Machine learning diabetes risk prediction platform with clinical feature analysis
     and predictive modeling published in peer-reviewed venue.

3. Self-Improving Code Agent:
   - Autonomous code generation agent with an integrated critique evaluation loop
     and long-term vector memory powered by ChromaDB.

4. SheetSense AI:
   - Conversational AI agent for natural language querying and dynamic visualization
     of complex spreadsheet datasets.

5. IntelliGlove:
   - IoT gesture recognition system translating sign gestures into text/speech.

6. InterviewPro:
   - AI-driven interview preparation platform with mock technical assessments
     and real-time evaluation rubrics.
""".strip()

_SYSTEM_PROMPT = f"""You are the Info Agent for the Orchestrator system.
Your mission is to provide clear, helpful, and technically accurate explanations about:
1. Farhan Aaqil's projects, experience, and background:
{AAQIL_PORTFOLIO}
2. How the Orchestrator works:
   - Command Routing: Natural language classifier routing commands with empirical confidence scores.
   - Approval Gate: Unbypassable human-in-the-loop gate using SQLite Compare-And-Set (CAS) atomic locking.
     Callers cannot alter or substitute payloads at execution time (zero-parameter contract).
   - Circuit Breakers: Protects against external LLM outages with 3-failure threshold and 30s cooldown.
   - Multi-Step Pipelines: Automated workflows (apply, publish, research) audited with per-stage latency logs.
3. The Fleet of 9 Autonomous Specialized Agents:
   - general_chat_agent (Toji): Farhan Aaqil's central intelligent orchestration companion, razor-sharp operator, and executive systems architect.
   - email_agent: Inbox inspection, reading unread messages, recruiter outreach drafting, and human-gated email dispatch.
   - github_agent: GitHub repository inspection, commit history, README/commit drafting, and human-gated issue/comment creation.
   - linkedin_agent: LinkedIn networking, recruiter discovery, 300-char connection notes, cold DMs, profile optimization, and human-gated post publishing.
   - career_agent: Resumes, cover letters, career planning, skill-gap analysis, and technical interview prep.
   - research_agent: ArXiv literature retrieval, synthesis, state-of-the-art tracking, journal checking, and IEEE formatting.
   - growth_content_agent: Technical blog posts for Dev.to/Hashnode/Medium, social threads, devlogs, and human-gated publishing.
   - critic_agent: Objective rubric scoring, adversarial code review, editorial critique, and improvement feedback.
   - info_agent: System documentation, Farhan Aaqil's portfolio, system architecture explanations, and cluster telemetry.
4. General Conversational Queries ("Common Talk"):
   - Greet politely, answer general questions, explain how to use the system, and guide the user on which of the 9 agents to run for their goals.

Maintain an approachable, technical, and concise tone. Format responses with clean markdown."""


def _call_llm(prompt: str) -> str:
    """Make an LLM completion call via Groq."""
    settings = get_settings()
    try:
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.router_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=2500,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.warning("[info_agent] LLM call failed: %s — providing structured documentation.", exc)
        return (
            "### Orchestrator Information & Architecture\n\n"
            "**Developer**: Farhan Aaqil (B.Tech AI/ML, JPNCE Mahbubnagar 2027)\n\n"
            "**Fleet of 9 Agents**:\n"
            "- **Toji (general_chat_agent)**: Central companion, executive operator, and systems architect.\n"
            "- **Email Agent**: Inbox inspection, recruiter outreach drafting, and gated email sending.\n"
            "- **GitHub Agent**: Repo inspection, README/commit drafting, and gated issue creation.\n"
            "- **LinkedIn Agent**: Recruiter search, 300-char connection notes, and gated post publishing.\n"
            "- **Career Agent**: Resume tailoring, skill-gap analysis, and cover letters.\n"
            "- **Research Agent**: ArXiv paper retrieval, synthesis, and journal evaluation.\n"
            "- **Growth Agent**: Technical blog posts and devlogs with gated publishing.\n"
            "- **Critic Agent**: Objective rubric scoring and adversarial quality critiques.\n"
            "- **Info Agent**: Portfolio insights, system documentation, and architecture explanation.\n\n"
            "**Key Projects**:\n"
            "- **Orchestrator Agent**: Multi-agent control plane with unbypassable approval gate, CAS concurrency, and fail-fast circuit breaker.\n"
            "- **DiaPredict AI**: Machine learning diabetes prediction (*Published Research 2025*).\n"
            "- **Self-Improving Code Agent**: Vector-memory assisted LLM code synthesis with critique loop.\n"
            "- **SheetSense AI**: Conversational spreadsheet intelligence platform.\n"
            "- **IntelliGlove & InterviewPro**: IoT gesture recognition and technical interview simulators.\n\n"
            "**How to Use the Orchestrator**:\n"
            "- Use **Dispatch Studio** for direct commands and conversational collaboration with Toji and the 9-agent fleet.\n"
            "- Use **Pipelines** for end-to-end multi-step automated workflows.\n"
            "- Use **Approvals Gate** to review and authorize sensitive actions with atomic zero-parameter safety."
        )


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the info agent.
    Provides system documentation, project knowledge, and conversational responses.
    """
    logger.info("[info_agent] Processing query: %.80s", command)
    output = _call_llm(command)
    return AgentResult(
        agent="info_agent",
        output=output,
        metadata=metadata or {},
    )
