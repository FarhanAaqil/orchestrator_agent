"""
orchestrator_core/agents/__init__.py

Fleet of 9 specialized autonomous agents:
  1. career_agent: Resumes, cover letters, career planning, skill-gap analysis.
  2. critic_agent: Objective rubric scoring, adversarial code review, editorial critique.
  3. email_agent: Inbox inspection, recruiter outreach drafting, gated email sending.
  4. general_chat_agent: Toji, central orchestration companion, high-speed operator.
  5. github_agent: GitHub repository inspection, README/commit drafting, gated issue creation.
  6. growth_content_agent: Technical blog posts, devlogs, gated publishing.
  7. info_agent: System documentation, portfolio insights, cluster telemetry.
  8. linkedin_agent: Recruiter networking, 300-char notes, gated post publishing.
  9. research_agent: ArXiv paper retrieval, literature synthesis, journal verification.
"""

from orchestrator_core.agents import (
    career_agent,
    critic_agent,
    email_agent,
    general_chat_agent,
    github_agent,
    growth_content_agent,
    info_agent,
    linkedin_agent,
    research_agent,
)

__all__ = [
    "career_agent",
    "critic_agent",
    "email_agent",
    "general_chat_agent",
    "github_agent",
    "growth_content_agent",
    "info_agent",
    "linkedin_agent",
    "research_agent",
]
