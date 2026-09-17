"""
tests/test_approval_gate.py

Unit tests for orchestrator_core/core/approval_gate.py

CONTRACT UNDER TEST:
  - execute_approved() never accepts a payload argument (enforced by signature)
  - All state transitions are guarded — no invalid jumps allowed
  - The CAS update prevents double execution
  - Expired approvals are caught before dispatch
  - _dispatch_action is a stub; all exceptions from it leave the row in 'executing'
"""

import inspect
import sqlite3
import time

import pytest

from orchestrator_core.core.approval_gate import (
    approve,
    execute_approved,
    reject,
    request_approval,
)
from orchestrator_core.exceptions import (
    ApprovalAlreadyExecutedError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalNotGrantedError,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _queue(db: sqlite3.Connection, action_type: str = "send_email", **payload_kw) -> str:
    """Queue a test approval and return its id."""
    payload = {"to": "test@example.com", **payload_kw}
    return request_approval(action_type, payload, db)


# ── Gate state tests ───────────────────────────────────────────────────────────

def test_execute_approved_no_record_raises(db):
    """Executing a nonexistent id raises ApprovalNotFoundError."""
    with pytest.raises(ApprovalNotFoundError):
        execute_approved("nonexistent-id", db)


def test_execute_approved_pending_raises(db):
    """Executing a pending (unapproved) record raises ApprovalNotGrantedError."""
    aid = _queue(db)
    with pytest.raises(ApprovalNotGrantedError):
        execute_approved(aid, db)


def test_execute_approved_rejected_raises(db):
    """Executing a rejected record raises ApprovalNotGrantedError."""
    aid = _queue(db)
    reject(aid, db)
    with pytest.raises(ApprovalNotGrantedError):
        execute_approved(aid, db)


def test_execute_approved_expired_raises(db):
    """Approvals past their expires_at are rejected with ApprovalExpiredError."""
    from datetime import datetime, timedelta, timezone

    aid = _queue(db, expiry_hours=0)

    # Force expires_at into the past
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with db:
        db.execute("UPDATE approvals SET expires_at = ? WHERE id = ?", (past, aid))

    approve(aid, db)

    with pytest.raises(ApprovalExpiredError):
        execute_approved(aid, db)

    # Verify the row was transitioned to 'expired'
    row = db.execute("SELECT status FROM approvals WHERE id = ?", (aid,)).fetchone()
    assert row["status"] == "expired"


def test_execute_approved_already_executed_raises(db):
    """Replaying an already-executed approval raises ApprovalAlreadyExecutedError."""
    aid = _queue(db)
    approve(aid, db)
    execute_approved(aid, db)

    with pytest.raises(ApprovalAlreadyExecutedError):
        execute_approved(aid, db)


def test_execute_approved_succeeds_once(db):
    """Happy path — pending → approved → executed, row ends in 'executed' status."""
    aid = _queue(db)
    approve(aid, db)
    execute_approved(aid, db)

    row = db.execute("SELECT status, executed_at FROM approvals WHERE id = ?", (aid,)).fetchone()
    assert row["status"] == "executed"
    assert row["executed_at"] is not None


def test_request_approval_stores_canonical_payload(db):
    """Stored payload_json must be canonically sorted — no whitespace, sorted keys."""
    import json

    aid = request_approval("send_email", {"z": 1, "a": 2}, db)
    row = db.execute("SELECT payload_json FROM approvals WHERE id = ?", (aid,)).fetchone()
    stored = row["payload_json"]

    # Must be parseable
    parsed = json.loads(stored)
    assert parsed == {"z": 1, "a": 2}

    # Keys must be sorted (canonical form)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


# ── SDK safety contract ────────────────────────────────────────────────────────

def test_no_payload_parameter_exists():
    """
    execute_approved() must NOT have a 'payload' parameter.

    This is a hard contract: callers cannot supply a different payload than
    what was stored in the DB row. If this test fails, someone added a payload
    arg — revert it immediately.
    """
    sig = inspect.signature(execute_approved)
    assert "payload" not in sig.parameters, (
        "SECURITY VIOLATION: execute_approved() must not accept a payload argument. "
        "Callers must never be able to substitute the approved payload."
    )


def test_approve_then_reject_raises(db):
    """Cannot reject an already-approved record."""
    aid = _queue(db)
    approve(aid, db)
    with pytest.raises(ApprovalNotGrantedError):
        reject(aid, db)


def test_reject_then_approve_raises(db):
    """Cannot approve an already-rejected record."""
    aid = _queue(db)
    reject(aid, db)
    with pytest.raises(ApprovalNotGrantedError):
        approve(aid, db)
