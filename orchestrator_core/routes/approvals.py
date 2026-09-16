"""
orchestrator_core/routes/approvals.py

Approval management HTTP routes.

  GET  /approvals              — list approvals with optional status filter + pagination
  POST /approvals/{id}/approve — mark a pending approval as approved
  POST /approvals/{id}/reject  — mark a pending approval as rejected
  POST /approvals/{id}/execute — execute an approved record (calls execute_approved)
"""

import sqlite3
import logging
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from orchestrator_core.storage.db import get_db_connection
from orchestrator_core.core.approval_gate import approve, reject, execute_approved, request_approval
from orchestrator_core.models import ApprovalRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Approvals"])


class ApprovalListResponse(BaseModel):
    items: list[dict]
    total: int
    limit: int
    offset: int


class ApprovalStatusUpdate(BaseModel):
    id: str
    status: str
    action_type: str


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """List approval records with optional status filter and pagination."""
    if status:
        rows = db.execute(
            "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        ).fetchall()
        total = db.execute(
            "SELECT COUNT(*) FROM approvals WHERE status = ?", (status,)
        ).fetchone()[0]
    else:
        rows = db.execute(
            "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    return ApprovalListResponse(
        items=[dict(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{approval_id}/approve", response_model=ApprovalStatusUpdate)
async def approve_action(
    approval_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Mark a pending approval as approved."""
    approve(approval_id, db)
    row = db.execute(
        "SELECT id, status, action_type FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()
    return ApprovalStatusUpdate(id=row["id"], status=row["status"], action_type=row["action_type"])


@router.post("/{approval_id}/reject", response_model=ApprovalStatusUpdate)
async def reject_action(
    approval_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Mark a pending approval as rejected."""
    reject(approval_id, db)
    row = db.execute(
        "SELECT id, status, action_type FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()
    return ApprovalStatusUpdate(id=row["id"], status=row["status"], action_type=row["action_type"])


@router.post("/{approval_id}/execute")
async def execute_action(
    approval_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Execute an approved action (loads payload from DB, no caller-supplied payload)."""
    execute_approved(approval_id, db)
    return {"approval_id": approval_id, "status": "executed"}
