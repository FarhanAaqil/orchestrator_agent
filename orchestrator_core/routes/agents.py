"""
orchestrator_core/routes/agents.py

Endpoints for inspecting supported agent metadata and capability roster.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    free_capabilities: list[str]
    gated_capabilities: list[str]
    is_active: bool = True


AGENTS_REGISTRY: list[AgentInfo] = [
    AgentInfo(
        id="general_chat_agent",
        name="Jarvis Companion",
        description="Conversational partner, technical sounding board, and high-level assistant.",
        icon="message-square",
        free_capabilities=["Casual discussion", "Architecture brainstorm", "Fleet orientation", "Technical explanations"],
        gated_capabilities=[],
    ),
    AgentInfo(
        id="email_agent",
        name="Email Agent",
        description="Inbox reader, recruiter outreach drafter, and communication specialist.",
        icon="mail",
        free_capabilities=["Check unread inbox", "Summarize email threads", "Draft recruiter emails", "Follow-up drafts"],
        gated_capabilities=["Send email (requires approval gate)"],
    ),
    AgentInfo(
        id="github_agent",
        name="GitHub Agent",
        description="Repository inspector, commit assistant, and documentation manager.",
        icon="github",
        free_capabilities=["List repositories", "Inspect profiles", "Generate READMEs", "Commit messages", "PR reviews"],
        gated_capabilities=["Create issues (requires approval gate)", "Post PR/issue comments (requires approval gate)"],
    ),
    AgentInfo(
        id="linkedin_agent",
        name="LinkedIn Agent",
        description="Professional networking, recruiter discovery, and branding assistant.",
        icon="linkedin",
        free_capabilities=["Search recruiters via web", "300-char connection notes", "Cold DMs", "Profile headline review"],
        gated_capabilities=["Publish posts to LinkedIn (requires approval gate)"],
    ),
    AgentInfo(
        id="career_agent",
        name="Career Agent",
        description="Resume tailoring, interview preparation, and career growth roadmap.",
        icon="briefcase",
        free_capabilities=["Resume critique", "Cover letter drafting", "Skill gap analysis", "Interview questions"],
        gated_capabilities=[],
    ),
    AgentInfo(
        id="research_agent",
        name="Research Agent",
        description="Academic preprint discovery, literature synthesis, and paper writing.",
        icon="book-open",
        free_capabilities=["Search arXiv papers", "Download preprint abstracts", "Synthesize findings", "Citation formats"],
        gated_capabilities=[],
    ),
    AgentInfo(
        id="growth_content_agent",
        name="Growth Agent",
        description="Technical blog authoring and devlog distribution.",
        icon="trending-up",
        free_capabilities=["Draft technical articles", "Devlogs", "Content strategy", "Twitter threads"],
        gated_capabilities=["Publish to Dev.to (requires approval gate)", "Publish to Hashnode (requires approval gate)"],
    ),
    AgentInfo(
        id="critic_agent",
        name="Critic Agent",
        description="Adversarial evaluation, quality scoring, and proofreading.",
        icon="check-circle",
        free_capabilities=["Rubric evaluation", "Multi-criteria scoring", "Weakness detection", "Actionable feedback"],
        gated_capabilities=[],
    ),
    AgentInfo(
        id="info_agent",
        name="Info Agent",
        description="System documentation, Farhan Aaqil portfolio, and project deep-dives.",
        icon="info",
        free_capabilities=["Aaqil's portfolio & projects", "Architecture walkthrough", "Pipeline documentation"],
        gated_capabilities=[],
    ),
]


@router.get("", response_model=list[AgentInfo])
async def list_agents():
    """Return the complete roster of active orchestrator agents and their capabilities."""
    return AGENTS_REGISTRY
