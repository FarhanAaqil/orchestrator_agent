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
    """Shape of a row in the approvals table with SEC-01..08 hardening fields."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: str
    payload_json: str      # JSON string — immutable after creation
    target: Optional[str] = None
    payload_hash: Optional[str] = None
    status: Literal["pending", "approved", "rejected", "executing", "executed", "expired", "superseded"]
    idempotency_key: Optional[str] = None
    approval_signature: Optional[str] = None
    approved_hash: Optional[str] = None
    supersedes_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    decided_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None


class ApprovalRequest(BaseModel):
    """Body for POST /approvals (internal use — agents call request_approval(), not this directly)."""
    action_type: str
    payload: dict[str, Any]
    target: Optional[str] = None
    idempotency_key: Optional[str] = None


class ApprovalApproveRequest(BaseModel):
    """Body for POST /approvals/{id}/approve with TOCTOU expected_hash validation."""
    expected_hash: Optional[str] = None


class ApprovalRejectRequest(BaseModel):
    """Body for POST /approvals/{id}/reject."""
    reason: Optional[str] = None


class ApprovalEditRequest(BaseModel):
    """Body for POST /approvals/{id}/edit (SEC-06 edit-and-reapprove flow)."""
    payload: dict[str, Any]
    target: Optional[str] = None


class AuditLogRecord(BaseModel):
    """Shape of a row in the audit_log table (SEC-07)."""
    id: str
    actor: str
    event: str
    entity: Optional[str] = None
    entity_id: Optional[str] = None
    detail_json: Optional[str] = None
    created_at: datetime


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


class ErrorResponse(BaseModel):
    """Standard error shape for all 4xx/5xx responses."""
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None


# ── Job & Autonomy Engine models ──────────────────────────────────────────────

JobStatus = Literal[
    "queued",
    "running",
    "awaiting_approval",
    "awaiting_input",
    "succeeded",
    "failed",
    "cancelled",
    "expired",
]

JobStepKind = Literal["llm", "tool", "propose", "note", "error"]


class JobRecord(BaseModel):
    """Row shape in the jobs table (persistent work unit)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    thread_id: str
    parent_job_id: Optional[str] = None
    session_id: Optional[str] = None
    schedule_id: Optional[str] = None
    agent: str
    goal: str
    params_json: str = "{}"
    status: JobStatus = "queued"
    priority: int = 5
    attempts: int = 0
    max_attempts: int = 3
    not_before: Optional[datetime] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None
    step_count: int = 0
    max_steps: int = 25
    token_budget: int = 60000
    tokens_used: int = 0
    cost_usd: float = 0.0
    result_json: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobStepRecord(BaseModel):
    """Row shape in the job_steps table."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    idx: int
    kind: JobStepKind
    name: Optional[str] = None
    input_json: Optional[str] = None
    output_json: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_ms: Optional[int] = None
    ok: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobCreateRequest(BaseModel):
    """Body for POST /jobs."""
    agent: str
    goal: str
    params: dict[str, Any] = Field(default_factory=dict)
    thread_id: Optional[str] = None
    parent_job_id: Optional[str] = None
    session_id: Optional[str] = None
    priority: int = Field(default=5, ge=1, le=10)
    max_steps: int = Field(default=25, ge=1, le=100)
    token_budget: int = Field(default=60000, ge=1000)


class JobAnswerRequest(BaseModel):
    """Body for answering an awaiting_input job."""
    answer: str
    data: dict[str, Any] = Field(default_factory=dict)


class SystemFlagRecord(BaseModel):
    """Row in system_flags table."""
    key: str
    value: str
    updated_at: datetime


class KillSwitchRequest(BaseModel):
    """Body for POST /system/kill-switch."""
    on: bool
