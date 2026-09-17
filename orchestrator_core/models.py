"""
orchestrator_core/models.py

Shared Pydantic models used across routes, agents, and core logic.
Import from here — never define request/response shapes in route files directly.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
import uuid


# ── Router models ─────────────────────────────────────────────────────────────

class RouterResult(BaseModel):
    """Returned by /route when confidence is above the threshold."""
    agent: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class ClarificationNeeded(BaseModel):
    """Returned by /route and /dispatch when confidence < ROUTER_CONFIDENCE_THRESHOLD."""
    status: Literal["needs_clarification"] = "needs_clarification"
    candidates: list[str]
    reasoning: str


# ── Agent models ───────────────────────────────────────────────────────────────

class AgentResult(BaseModel):
    """Returned by every supported agent's handle() method."""
    agent: str
    output: str
    action_type: Optional[str] = None   # 'send_email', 'publish_hashnode', etc. if approval needed
    approval_id: Optional[str] = None    # set if the agent queued an approval request
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Approval models ────────────────────────────────────────────────────────────

class ApprovalRecord(BaseModel):
    """Shape of a row in the approvals table."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: str
    payload_json: str      # JSON string — immutable after creation
    status: Literal["pending", "approved", "rejected", "executing", "executed", "expired"]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None


class ApprovalRequest(BaseModel):
    """Body for POST /approvals (internal use — agents call request_approval(), not this directly)."""
    action_type: str
    payload: dict[str, Any]


# ── Pipeline models ────────────────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    """Body for POST /pipeline/{name}."""
    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class PipelineStepRecord(BaseModel):
    """One step in a pipeline run — written to pipeline_steps table."""
    run_id: str
    step_number: int
    agent_name: str
    input_json: str
    output_json: str
    latency_ms: int
    success: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None


class PipelineRunStatus(BaseModel):
    """Returned by GET /runs/{run_id}."""
    run_id: str
    pipeline_name: str
    status: Literal["running", "completed", "failed"]
    steps: list[PipelineStepRecord]
    started_at: datetime
    completed_at: Optional[datetime] = None


# ── Error envelope ─────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error shape for all 4xx/5xx responses."""
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
