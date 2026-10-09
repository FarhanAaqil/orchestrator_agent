"""
orchestrator_core/routes/agents.py

Endpoints for inspecting supported agent metadata, capability roster,
dynamic health indicators, circuit breaker statuses, and administrative enable/disable toggles.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from orchestrator_core.models import canonical_agent_name
from orchestrator_core.storage.db import get_db_connection
from orchestrator_core.tools.registry import default_registry, get_tool_circuit_status

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    free_capabilities: list[str]
    gated_capabilities: list[str]
    is_active: bool = True
    status: str = "healthy"  # "healthy", "degraded", "disabled"
    allowed_tools: list[str] = Field(default_factory=list)
    circuit_breakers: dict[str, str] = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    is_active: bool = Field(description="Enable or disable the agent.")


_BASE_AGENTS_METADATA: list[dict] = [
    {
        "id": "general_chat_agent",
        "name": "Toji",
        "description": "Farhan Aaqil's razor-sharp AI companion, executive operator, and systems architect.",
        "icon": "message-square",
        "free_capabilities": ["Casual discussion", "Architecture brainstorm", "Fleet orientation", "Technical explanations"],
        "gated_capabilities": [],
    },
    {
        "id": "email_agent",
        "name": "Email Agent",
        "description": "Inbox reader, recruiter outreach drafter, and communication specialist.",
        "icon": "mail",
        "free_capabilities": ["Check unread inbox", "Summarize email threads", "Draft recruiter emails", "Follow-up drafts"],
        "gated_capabilities": ["Send email (requires approval gate)"],
    },
    {
        "id": "github_agent",
        "name": "GitHub Agent",
        "description": "Repository inspector, commit assistant, and documentation manager.",
        "icon": "github",
        "free_capabilities": ["List repositories", "Inspect profiles", "Generate READMEs", "Commit messages", "PR reviews"],
        "gated_capabilities": ["Create issues (requires approval gate)", "Post PR/issue comments (requires approval gate)"],
    },
    {
        "id": "linkedin_agent",
        "name": "LinkedIn Agent",
        "description": "Professional networking, recruiter discovery, and branding assistant.",
        "icon": "linkedin",
        "free_capabilities": ["Search recruiters via web", "300-char connection notes", "Cold DMs", "Profile headline review"],
        "gated_capabilities": ["Publish posts to LinkedIn (requires approval gate)"],
    },
    {
        "id": "career_agent",
        "name": "Career Agent",
        "description": "Resume tailoring, interview preparation, and career growth roadmap.",
        "icon": "briefcase",
        "free_capabilities": ["Resume critique", "Cover letter drafting", "Skill gap analysis", "Interview questions"],
        "gated_capabilities": [],
    },
    {
        "id": "research_agent",
        "name": "Research Agent",
        "description": "Academic preprint discovery, literature synthesis, and paper writing.",
        "icon": "book-open",
        "free_capabilities": ["Search arXiv papers", "Download preprint abstracts", "Synthesize findings", "Citation formats"],
        "gated_capabilities": [],
    },
    {
        "id": "growth_content_agent",
        "name": "Growth Agent",
        "description": "Technical blog authoring and devlog distribution.",
        "icon": "trending-up",
        "free_capabilities": ["Draft technical articles", "Devlogs", "Content strategy", "Twitter threads"],
        "gated_capabilities": ["Publish to Dev.to (requires approval gate)", "Publish to Hashnode (requires approval gate)"],
    },
    {
        "id": "critic_agent",
        "name": "Critic Agent",
        "description": "Adversarial evaluation, quality scoring, and proofreading.",
        "icon": "check-circle",
        "free_capabilities": ["Rubric evaluation", "Multi-criteria scoring", "Weakness detection", "Actionable feedback"],
        "gated_capabilities": [],
    },
    {
        "id": "info_agent",
        "name": "Info Agent",
        "description": "System documentation, Farhan Aaqil portfolio, and project deep-dives.",
        "icon": "info",
        "free_capabilities": ["Aaqil's portfolio & projects", "Architecture walkthrough", "Pipeline documentation"],
        "gated_capabilities": [],
    },
]


def _build_agent_info(meta: dict, db: sqlite3.Connection) -> AgentInfo:
    """Build dynamic AgentInfo with active status, allowed tools, and circuit breaker health."""
    agent_id = meta["id"]

    # Check administrative toggle in system_flags
    flag_key = f"agent_enabled_{agent_id}"
    row = db.execute("SELECT value FROM system_flags WHERE key = ?", (flag_key,)).fetchone()
    is_active = (row["value"] != "0") if row else True

    # Resolve allowed tools
    allowed_tools = sorted(list(default_registry.for_agent(agent_id).keys()))

    # Resolve circuit breaker states for tools used by this agent
    tool_breakers = get_tool_circuit_status()
    agent_breakers = {t: tool_breakers[t] for t in allowed_tools if t in tool_breakers}

    if not is_active:
        health_status = "disabled"
    elif any(state == "OPEN" for state in agent_breakers.values()):
        health_status = "degraded"
    else:
        health_status = "healthy"

    return AgentInfo(
        id=agent_id,
        name=meta["name"],
        description=meta["description"],
        icon=meta["icon"],
        free_capabilities=meta["free_capabilities"],
        gated_capabilities=meta["gated_capabilities"],
        is_active=is_active,
        status=health_status,
        allowed_tools=allowed_tools,
        circuit_breakers=agent_breakers,
    )


@router.get("", response_model=list[AgentInfo])
async def list_agents(db: sqlite3.Connection = Depends(get_db_connection)):
    """Return the complete roster of orchestrator agents with live health and tool statuses."""
    return [_build_agent_info(meta, db) for meta in _BASE_AGENTS_METADATA]


@router.get("/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str, db: sqlite3.Connection = Depends(get_db_connection)):
    """Retrieve detailed metadata and health for a single agent."""
    canonical = canonical_agent_name(agent_id)
    match = next((m for m in _BASE_AGENTS_METADATA if m["id"] in (agent_id, canonical)), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent '{agent_id}' not found.")
    return _build_agent_info(match, db)


@router.patch("/{agent_id}", response_model=AgentInfo)
async def update_agent_status(
    agent_id: str,
    body: AgentUpdateRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Enable or disable an agent in system_flags."""
    canonical = canonical_agent_name(agent_id)
    match = next((m for m in _BASE_AGENTS_METADATA if m["id"] in (agent_id, canonical)), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent '{agent_id}' not found.")

    flag_key = f"agent_enabled_{match['id']}"
    flag_val = "1" if body.is_active else "0"
    now_iso = datetime.now(timezone.utc).isoformat()

    with db:
        db.execute(
            """
            INSERT INTO system_flags (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (flag_key, flag_val, now_iso),
        )

    return _build_agent_info(match, db)
