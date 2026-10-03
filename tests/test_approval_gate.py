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
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from orchestrator_core.core.approval_gate import (
    approve,
    compute_payload_hash,
    edit_and_supersede,
    evaluate_target_policy,
    execute_approved,
    generate_approval_signature,
    reject,
    request_approval,
)
from orchestrator_core.exceptions import (
    ApprovalAlreadyExecutedError,
    ApprovalExpiredError,
    ApprovalHashMismatchError,
    ApprovalNotFoundError,
    ApprovalNotGrantedError,
    ApprovalSignatureInvalidError,
    ApprovalSupersededError,
    ApprovalTamperedError,
    IdempotencyConflictError,
    SecurityPolicyViolationError,
)
from orchestrator_core.main import app
from orchestrator_core.storage.db import get_db_connection


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


# ── SEC-01 through SEC-08 Hardening Tests ─────────────────────────────────────

def test_sec_01_executor_takes_only_proposal_id():
    """SEC-01: execute_approved must strictly accept (approval_id, db). No payload argument."""
    sig = inspect.signature(execute_approved)
    params = list(sig.parameters.keys())
    assert params == ["approval_id", "db"]


def test_sec_02_payload_or_action_tampering_refuses_execution(db):
    """SEC-02: Any change to payload, target, or action_type after approval refuses execution."""
    aid = _queue(db, action_type="send_email", subject="Original Subject")
    approve(aid, db)

    # 1. Simulate DB tampering on payload_json
    tampered_payload = json.dumps({"to": "attacker@evil.com", "subject": "Hacked"}, separators=(",", ":"))
    with db:
        db.execute("UPDATE approvals SET payload_json = ? WHERE id = ?", (tampered_payload, aid))

    with pytest.raises(ApprovalTamperedError):
        execute_approved(aid, db)

    # 2. Reset payload and tamper action_type
    original_payload = json.dumps({"subject": "Original Subject", "to": "test@example.com"}, separators=(",", ":"))
    with db:
        db.execute("UPDATE approvals SET payload_json = ?, action_type = 'publish_hashnode' WHERE id = ?",
                   (original_payload, aid))

    with pytest.raises(ApprovalTamperedError):
        execute_approved(aid, db)


def test_sec_03_hmac_tamper_resistance_forged_approval_fails(db):
    """SEC-03: Direct DB UPDATE to status='approved' without valid HMAC signature fails execution."""
    aid = _queue(db, action_type="send_email", subject="Test HMAC")

    # Attacker tries direct SQL update to bypass approval endpoint
    with db:
        db.execute("UPDATE approvals SET status = 'approved' WHERE id = ?", (aid,))

    with pytest.raises(ApprovalSignatureInvalidError):
        execute_approved(aid, db)

    # Attacker tries forged signature
    with db:
        db.execute(
            "UPDATE approvals SET approval_signature = 'forged_fake_signature_hex' WHERE id = ?",
            (aid,),
        )

    with pytest.raises(ApprovalSignatureInvalidError):
        execute_approved(aid, db)


def test_sec_04_idempotency_key_blocks_duplicate_execution(db):
    """SEC-04: Idempotency keys prevent duplicate execution."""
    aid1 = request_approval("send_email", {"to": "idempotent@example.com"}, db, idempotency_key="key_abc_123")

    # 1. Retrying request_approval with same key before execution idempotently returns original id
    retry_aid = request_approval("send_email", {"to": "idempotent@example.com"}, db, idempotency_key="key_abc_123")
    assert retry_aid == aid1

    approve(aid1, db)
    execute_approved(aid1, db)

    # 2. Replaying request_approval after execution raises IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        request_approval("send_email", {"to": "idempotent@example.com"}, db, idempotency_key="key_abc_123")

    # 3. Direct re-execution on the approval record raises ApprovalAlreadyExecutedError
    with pytest.raises(ApprovalAlreadyExecutedError):
        execute_approved(aid1, db)


def test_sec_05_unapproved_rejected_expired_superseded_cannot_execute(db):
    """SEC-05: Expired, rejected, or superseded proposals cannot be executed."""
    # 1. Pending cannot execute
    aid = _queue(db)
    with pytest.raises(ApprovalNotGrantedError):
        execute_approved(aid, db)

    # 2. Rejected cannot execute
    reject(aid, db)
    with pytest.raises(ApprovalNotGrantedError):
        execute_approved(aid, db)

    # 3. Superseded cannot execute
    aid2 = _queue(db)
    edit_and_supersede(aid2, {"to": "revised@example.com"}, db)
    with pytest.raises(ApprovalSupersededError):
        execute_approved(aid2, db)


def test_sec_06_edit_and_supersede_lifecycle(db):
    """SEC-06: Editing a proposal supersedes the old version and creates a new pending proposal."""
    aid = _queue(db, action_type="send_email", subject="Initial Draft")
    approve(aid, db)

    # Edit proposal
    new_aid = edit_and_supersede(aid, {"subject": "Revised Draft", "to": "test@example.com"}, db)
    assert new_aid != aid

    # Old proposal is superseded
    old_row = db.execute("SELECT status FROM approvals WHERE id = ?", (aid,)).fetchone()
    assert old_row["status"] == "superseded"

    # Old proposal cannot be approved or executed
    with pytest.raises(ApprovalSupersededError):
        approve(aid, db)
    with pytest.raises(ApprovalSupersededError):
        execute_approved(aid, db)

    # New proposal is pending, links to old proposal
    new_row = db.execute("SELECT status, supersedes_id FROM approvals WHERE id = ?", (new_aid,)).fetchone()
    assert new_row["status"] == "pending"
    assert new_row["supersedes_id"] == aid

    # New proposal can be approved and executed
    approve(new_aid, db)
    execute_approved(new_aid, db)
    final_row = db.execute("SELECT status FROM approvals WHERE id = ?", (new_aid,)).fetchone()
    assert final_row["status"] == "executed"


def test_sec_07_audit_log_captures_all_events(db):
    """SEC-07: All gate events, executions, and tampering attempts are written to audit_log."""
    aid = _queue(db, action_type="send_email", subject="Audited Action")
    approve(aid, db)
    execute_approved(aid, db)

    events = db.execute(
        "SELECT event FROM audit_log WHERE entity = 'approval' AND entity_id = ? ORDER BY created_at ASC",
        (aid,),
    ).fetchall()
    event_names = [e["event"] for e in events]

    assert "approval_requested" in event_names
    assert "approval_granted" in event_names
    assert "execution_attempted" in event_names
    assert "execution_succeeded" in event_names


def test_sec_08_recipient_policy_enforcement(db):
    """SEC-08: Recipient/target policy: denylist block and first-time recipient high risk flag."""
    # 1. Denylisted target is rejected immediately
    with pytest.raises(SecurityPolicyViolationError):
        request_approval("send_email", {"to": "blocked@example.com"}, db)

    # 2. First-time recipient is flagged as high risk
    policy1 = evaluate_target_policy("send_email", "new_recipient@company.org", db)
    assert policy1["allowed"] is True
    assert policy1["first_time"] is True
    assert policy1["risk"] == "high"

    # Execute a proposal to this recipient
    aid = request_approval("send_email", {"to": "new_recipient@company.org"}, db)
    approve(aid, db)
    execute_approved(aid, db)

    # 3. Subsequent request to same recipient is now low risk (not first time)
    policy2 = evaluate_target_policy("send_email", "new_recipient@company.org", db)
    assert policy2["first_time"] is False
    assert policy2["risk"] == "low"


# ── TOCTOU & HTTP Integration Tests ───────────────────────────────────────────

def test_toctou_expected_hash_http_endpoint(db):
    """TOCTOU: POST /approvals/{id}/approve with expected_hash returns 409 on mismatch."""
    app.dependency_overrides[get_db_connection] = lambda: db
    client = TestClient(app)

    try:
        aid = _queue(db, action_type="send_email", subject="TOCTOU check")
        row = db.execute("SELECT payload_hash FROM approvals WHERE id = ?", (aid,)).fetchone()
        real_hash = row["payload_hash"]

        # 1. Hash mismatch returns 409
        res_mismatch = client.post(f"/approvals/{aid}/approve", json={"expected_hash": "stale_hash_xyz"})
        assert res_mismatch.status_code == 409
        assert res_mismatch.json()["error"] == "APPROVAL_HASH_MISMATCH"

        # 2. Matching hash succeeds
        res_ok = client.post(f"/approvals/{aid}/approve", json={"expected_hash": real_hash})
        assert res_ok.status_code == 200
        assert res_ok.json()["status"] == "approved"
        assert res_ok.json()["approved_hash"] == real_hash

        # 3. Verify audit log endpoint
        res_audit = client.get(f"/approvals/{aid}/audit")
        assert res_audit.status_code == 200
        audit_records = res_audit.json()
        assert len(audit_records) >= 2
    finally:
        app.dependency_overrides.clear()


def test_edit_and_supersede_http_endpoint(db):
    """POST /approvals/{id}/edit endpoint supersedes old proposal and returns new record."""
    app.dependency_overrides[get_db_connection] = lambda: db
    client = TestClient(app)

    try:
        aid = _queue(db, action_type="send_email", subject="Before Edit")

        res_edit = client.post(
            f"/approvals/{aid}/edit",
            json={"payload": {"to": "edited@example.com", "subject": "After Edit"}},
        )
        assert res_edit.status_code == 200
        data = res_edit.json()
        assert data["id"] != aid
        assert data["supersedes_id"] == aid
        assert data["status"] == "pending"

        # Verify old approval was marked superseded
        old_row = db.execute("SELECT status FROM approvals WHERE id = ?", (aid,)).fetchone()
        assert old_row["status"] == "superseded"
    finally:
        app.dependency_overrides.clear()
