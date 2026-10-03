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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from orchestrator_core.storage.db import get_db_connection
from orchestrator_core.core.approval_gate import (
    approve,
    reject,
    execute_approved,
    edit_and_supersede,
)
from orchestrator_core.models import (
    ApprovalRecord,
    ApprovalApproveRequest,
    ApprovalRejectRequest,
    ApprovalEditRequest,
)

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
    payload_hash: Optional[str] = None
    approved_hash: Optional[str] = None


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


@router.get("/{approval_id}", response_model=ApprovalRecord)
async def get_approval(
    approval_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Retrieve a single approval record by ID."""
    row = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Approval record {approval_id} not found")
    return ApprovalRecord(**dict(row))


@router.post("/{approval_id}/approve", response_model=ApprovalStatusUpdate)
async def approve_action(
    approval_id: str,
    body: Optional[ApprovalApproveRequest] = None,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """
    Mark a pending approval as approved.
    TOCTOU: If body.expected_hash is provided, rejects with 409 if hash mismatch.
    """
    expected_hash = body.expected_hash if body else None
    approve(approval_id, db, expected_hash=expected_hash)
    row = db.execute(
        "SELECT id, status, action_type, payload_hash, approved_hash FROM approvals WHERE id = ?",
        (approval_id,),
    ).fetchone()
    return ApprovalStatusUpdate(
        id=row["id"],
        status=row["status"],
        action_type=row["action_type"],
        payload_hash=row["payload_hash"],
        approved_hash=row["approved_hash"],
    )


@router.post("/{approval_id}/reject", response_model=ApprovalStatusUpdate)
async def reject_action(
    approval_id: str,
    body: Optional[ApprovalRejectRequest] = None,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Mark a pending approval as rejected."""
    reason = body.reason if body else None
    reject(approval_id, db, reason=reason)
    row = db.execute(
        "SELECT id, status, action_type, payload_hash, approved_hash FROM approvals WHERE id = ?",
        (approval_id,),
    ).fetchone()
    return ApprovalStatusUpdate(
        id=row["id"],
        status=row["status"],
        action_type=row["action_type"],
        payload_hash=row["payload_hash"],
        approved_hash=row["approved_hash"],
    )


@router.post("/{approval_id}/edit", response_model=ApprovalRecord)
async def edit_approval_action(
    approval_id: str,
    body: ApprovalEditRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """SEC-06: Supersede existing approval and create a new pending proposal."""
    new_id = edit_and_supersede(approval_id, body.payload, db, new_target=body.target)
    row = db.execute("SELECT * FROM approvals WHERE id = ?", (new_id,)).fetchone()
    return ApprovalRecord(**dict(row))


@router.post("/{approval_id}/execute")
async def execute_action(
    approval_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Execute an approved action (loads payload from DB, no caller-supplied payload)."""
    execute_approved(approval_id, db)
    return {"approval_id": approval_id, "status": "executed"}


@router.get("/{approval_id}/audit")
async def get_approval_audit_trail(
    approval_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """SEC-07: Retrieve full audit trail for an approval record."""
    rows = db.execute(
        "SELECT * FROM audit_log WHERE entity = 'approval' AND entity_id = ? ORDER BY created_at ASC",
        (approval_id,),
    ).fetchall()
    return [dict(r) for r in rows]
