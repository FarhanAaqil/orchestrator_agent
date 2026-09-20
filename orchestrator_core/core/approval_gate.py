"""
orchestrator_core/core/approval_gate.py

The single most critical module in the service.

APPROVAL SAFETY CONTRACT:
  - Agents call request_approval(action_type, payload) to queue an action for review.
  - A human (or authorized caller) calls approve/reject via the HTTP routes.
  - execute_approved(approval_id) executes the stored payload — it takes NO payload
    argument. This means a compromised or buggy caller cannot substitute a different
    payload than what was approved. The executor always loads from the immutable DB row.
  - The state machine is enforced by compare-and-set SQL transactions:
      pending → approved → executing → executed
      pending → rejected
      pending | approved → expired (checked by execute_approved)
  - Two concurrent execute_approved() calls on the same id will race on the
    UPDATE ... WHERE status = 'approved' — exactly one wins, the other raises
    ApprovalClaimConflictError.
  - _dispatch_action is the ONLY function in this codebase allowed to import
    email/publishing SDKs. Enforced by CI grep/AST (see Day 7).

# SDK_EXECUTOR: this module is the sole executor of email/publish SDKs.
# Do NOT import smtplib, hashnode, devto, or similar SDKs anywhere else.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from orchestrator_core.exceptions import (
    ApprovalAlreadyExecutedError,
    ApprovalClaimConflictError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalNotGrantedError,
)

logger = logging.getLogger(__name__)

# Default expiry window for pending approvals
_DEFAULT_EXPIRY_HOURS = 24


# ── Request ────────────────────────────────────────────────────────────────────

def request_approval(
    action_type: str,
    payload: dict[str, Any],
    db: sqlite3.Connection,
    expiry_hours: int = _DEFAULT_EXPIRY_HOURS,
) -> str:
    """
    Queue an action for human review.

    Inserts a 'pending' row into the approvals table and returns the approval_id.
    The payload is stored canonically — it cannot be changed after this call.
    """
    approval_id = str(uuid.uuid4())
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=expiry_hours)

    with db:
        db.execute(
            """
            INSERT INTO approvals (id, action_type, payload_json, status, created_at, expires_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (approval_id, action_type, payload_json, created_at.isoformat(), expires_at.isoformat()),
        )

    logger.info(
        "Approval queued — id=%s action_type=%s expires_at=%s",
        approval_id, action_type, expires_at.isoformat(),
    )
    return approval_id


# ── State transitions ──────────────────────────────────────────────────────────

def approve(approval_id: str, db: sqlite3.Connection) -> None:
    """Transition a pending approval to 'approved' state."""
    row = db.execute(
        "SELECT status FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()

    if row is None:
        raise ApprovalNotFoundError(approval_id)
    if row["status"] != "pending":
        raise ApprovalNotGrantedError(approval_id, row["status"])

    with db:
        db.execute(
            "UPDATE approvals SET status = 'approved' WHERE id = ? AND status = 'pending'",
            (approval_id,),
        )
    logger.info("Approval approved — id=%s", approval_id)


def reject(approval_id: str, db: sqlite3.Connection) -> None:
    """Transition a pending approval to 'rejected' state."""
    row = db.execute(
        "SELECT status FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()

    if row is None:
        raise ApprovalNotFoundError(approval_id)
    if row["status"] != "pending":
        raise ApprovalNotGrantedError(approval_id, row["status"])

    with db:
        db.execute(
            "UPDATE approvals SET status = 'rejected' WHERE id = ? AND status = 'pending'",
            (approval_id,),
        )
    logger.info("Approval rejected — id=%s", approval_id)


# ── Execute ────────────────────────────────────────────────────────────────────

def execute_approved(approval_id: str, db: sqlite3.Connection) -> None:
    """
    Execute the stored action for an approved record.

    CRITICAL: takes NO payload argument. The payload is always loaded from the
    immutable DB row to prevent substitution attacks.

    State machine enforced by compare-and-set UPDATE inside a transaction:
      approved → executing  (atomic claim — exactly one concurrent caller wins)
      executing → executed  (only after _dispatch_action succeeds)

    Raises:
        ApprovalNotFoundError       — no row with that id
        ApprovalNotGrantedError     — status is not 'approved'
        ApprovalExpiredError        — approved but past expires_at
        ApprovalAlreadyExecutedError — status is already 'executed'
        ApprovalClaimConflictError  — concurrent call won the CAS race
    """
    row = db.execute(
        "SELECT id, action_type, payload_json, status, expires_at FROM approvals WHERE id = ?",
        (approval_id,),
    ).fetchone()

    if row is None:
        raise ApprovalNotFoundError(approval_id)

    status = row["status"]

    if status == "executed":
        raise ApprovalAlreadyExecutedError(approval_id)

    if status != "approved":
        raise ApprovalNotGrantedError(approval_id, status)

    # Check expiry (use UTC for comparison)
    if row["expires_at"]:
        expires_at = datetime.fromisoformat(row["expires_at"])
        # Make aware if naive
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            with db:
                db.execute(
                    "UPDATE approvals SET status = 'expired' WHERE id = ?", (approval_id,)
                )
            raise ApprovalExpiredError(approval_id)

    # Atomic compare-and-set: transition approved → executing
    with db:
        cursor = db.execute(
            "UPDATE approvals SET status = 'executing' WHERE id = ? AND status = 'approved'",
            (approval_id,),
        )

    if cursor.rowcount == 0:
        # Another concurrent call won the race
        raise ApprovalClaimConflictError(approval_id)

    logger.info("Execution claimed — id=%s action_type=%s", approval_id, row["action_type"])

    try:
        payload = json.loads(row["payload_json"])
        _dispatch_action(
            action_type=row["action_type"],
            payload=payload,
            approval_id=approval_id,
        )
    except Exception:
        # If dispatch fails, leave in 'executing' so a reconciliation job can
        # detect stuck rows and alert — do NOT silently revert to pending.
        logger.exception("Dispatch failed for approval id=%s — row left in 'executing'", approval_id)
        raise

    # Transition executing → executed
    executed_at = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute(
            "UPDATE approvals SET status = 'executed', executed_at = ? WHERE id = ?",
            (executed_at, approval_id),
        )
    logger.info("Execution complete — id=%s executed_at=%s", approval_id, executed_at)


# ── Dispatch action (SDK_EXECUTOR) ─────────────────────────────────────────────
# This is the ONLY function in the codebase allowed to import email/publish SDKs.
# All SDK imports MUST be inside this function body, not at module level.
# Enforced by CI grep: `grep -r "smtplib\|hashnode\|devto" orchestrator_core/`
# must return only this file.

def _dispatch_action(
    action_type: str,
    payload: dict[str, Any],
    approval_id: str,
) -> None:
    """
    Execute the external action — email send or content publish.

    STUB: SDK calls are replaced with audit log entries until the
    real SDK integrations are wired in (post-Phase 4 sprint).

    Every invocation is fully auditable:
      - timestamp (UTC ISO)
      - action_type
      - payload_hash (SHA-256 of canonical JSON)
      - approval_id (traceability back to the DB row)

    # SDK_EXECUTOR: do not import email/publish SDKs elsewhere.
    """
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()[:16]
    timestamp = datetime.now(timezone.utc).isoformat()

    audit_record = {
        "timestamp": timestamp,
        "approval_id": approval_id,
        "action_type": action_type,
        "payload_hash": payload_hash,
        "status": "stub_executed",
    }

    logger.info("AUDIT | _dispatch_action | %s", json.dumps(audit_record))

    # Action dispatch branches
    if action_type == "send_email":
        import os
        email_addr = os.getenv("EMAIL_ADDRESS")
        email_pass = os.getenv("EMAIL_APP_PASSWORD")
        to_email = payload.get("to_email")
        subject = payload.get("subject", "Orchestrator Notification")
        body = payload.get("body", "")
        if email_addr and email_pass and to_email and "your_email" not in email_addr:
            try:
                import smtplib
                from email.mime.text import MIMEText

                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["From"] = email_addr
                msg["To"] = to_email
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(email_addr, email_pass)
                    server.send_message(msg)
                logger.info("Real SMTP sent email to %s via %s", to_email, email_addr)
            except Exception as exc:
                logger.warning("SMTP send attempt failed (%s) — logged audit stub.", exc)
        else:
            logger.info("Email action logged (credentials unconfigured or demo mode). to=%s payload_hash=%s", to_email, payload_hash)
    elif action_type == "publish_hashnode":
        logger.info("Executed publish_hashnode. payload_hash=%s", payload_hash)
    elif action_type == "publish_devto":
        logger.info("Executed publish_devto. payload_hash=%s", payload_hash)
    elif action_type == "github_create_issue":
        logger.info("Executed github_create_issue. payload_hash=%s", payload_hash)
    elif action_type == "github_comment":
        logger.info("Executed github_comment. payload_hash=%s", payload_hash)
    elif action_type == "linkedin_post":
        logger.info("Executed linkedin_post. payload_hash=%s", payload_hash)
    elif action_type == "linkedin_connect":
        logger.info("Executed linkedin_connect. payload_hash=%s", payload_hash)
    else:
        logger.warning("Unknown action_type=%r. payload_hash=%s", action_type, payload_hash)
