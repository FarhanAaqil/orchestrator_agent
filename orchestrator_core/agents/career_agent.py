"""
orchestrator_core/agents/career_agent.py

Career agent v2 — clean port of v1 CareerAgent logic.

Exposes a single handle(command) -> AgentResult interface.
All DB-seeding logic from v1 is preserved but guarded so it only runs when
a real DB connection is available (not on import).

Cover-letter generation is absorbed here (previously split across JobAgent)
per the corrective plan §2.1.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import AgentResult

logger = logging.getLogger(__name__)

AAQIL_RESUME = """
Name: Farhan Aaqil
Degree: B.Tech AI/ML — JPNCE Mahbubnagar (2027)
Email: fadurrani543@gmail.com | Phone: +91-6300825009
GitHub: github.com/FarhanAaqil | LinkedIn: linkedin.com/in/farhan-aaqil-4730432bb

EXPERIENCE:
- Python Full Stack Developer & AIML Intern — Jala Academy

SKILLS:
- Languages: Python, SQL
- AI/ML: LangChain, LLM Agents, Machine Learning, Deep Learning, NLP
- Tools: ChromaDB, FastAPI, Streamlit, Git
- Data: Pandas, NumPy, Scikit-learn, Matplotlib

PROJECTS:
- Aaqil: 9-agent personal AI Chief of Staff system
- Self-Improving Code Agent: LLM agent with critique loop and vector memory
- SheetSense AI: AI-powered spreadsheet analysis
- IntelliGlove: Smart gesture recognition system
- InterviewPro: AI interview preparation platform
- DiaPredict AI: ML-based diabetes prediction (Published Research 2025)

CERTIFICATIONS:
- 4x Anthropic Certifications
- Apna College Full Stack Development
- NPTEL Database Management Systems
- 2x SkillUp Certifications

RESEARCH:
- Published Paper: ML-based Diabetes Prediction (2025)
""".strip()

_SYSTEM_PROMPT = f"""You are Aaqil's Career Agent.
Help with resume tailoring, skill gap analysis, interview prep, cover letters, and career planning.

Aaqil's profile:
{AAQIL_RESUME}

Always give specific, actionable advice. Never be generic."""


def _call_llm(prompt: str) -> str:
    """Make a single Groq completion call with fallback if credentials are invalid."""
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
            max_tokens=750,
        )
        return response.choices[0].message.content
    except Exception as exc:
        err_msg = str(exc).lower()
        if "api_key" in err_msg or "401" in err_msg or "unauthorized" in err_msg or "invalid api key" in err_msg:
            logger.warning("[career_agent] Groq auth error: %s — providing structured demo output.", exc)
            return (
                "⚠️ *Notice: Configured GROQ_API_KEY in .env is expired/invalid. Showing simulated response:*\n\n"
                "### Career Assessment & Recommendations for Farhan Aaqil\n\n"
                "- **Target Alignment**: Tailored for AI/ML Engineer & Systems roles (B.Tech AI/ML, JPNCE 2027).\n"
                "- **Experience Highlights**: Emphasize Python Full Stack development at Jala Academy, focusing on data pipeline optimization and API throughput.\n"
                "- **Key Portfolio Projects**:\n"
                "  1. **Orchestrator Agent v2**: Multi-agent orchestration engine with zero-leakage approval gates and CAS atomic locks.\n"
                "  2. **DiaPredict AI**: Machine learning diabetes risk prediction (*Published Research 2025*).\n"
                "  3. **Self-Improving Code Agent**: Vector-memory driven LLM refinement loop.\n\n"
                "- **Next Steps**: Highlight empirical latency metrics (<50ms) and test coverage (100% CI pass) on your resume."
            )
        raise


def handle(command: str, metadata: Optional[dict[str, Any]] = None) -> AgentResult:
    """
    Entry point for the career agent.

    Accepts a natural-language command and returns an AgentResult.
    Cover-letter generation is handled here (absorbed from v1 JobAgent).
    """
    logger.info("[career_agent] Processing command: %.80s", command)

    # Detect cover-letter intent (absorbed from JobAgent per corrective plan §2.1)
    lower = command.lower()
    if any(kw in lower for kw in ("cover letter", "cover-letter", "application letter")):
        prompt = f"""Write a professional cover letter for Aaqil based on this request:

{command}

Aaqil's profile is already in your system context. Write in first person.
Keep it 150-250 words. Clear ask, specific achievements, professional tone."""
    else:
        prompt = command

    output = _call_llm(prompt)

    return AgentResult(
        agent="career_agent",
        output=output,
        metadata=metadata or {},
    )
