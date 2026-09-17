"""
tests/test_approval_concurrency.py

Concurrency and replay safety tests for orchestrator_core/core/approval_gate.py.

Guarantees under test:
  1. Atomic claim: Two threads attempting to execute the same approved record simultaneously
     race on CAS — exactly one succeeds, the other fails with ApprovalClaimConflictError or
     ApprovalAlreadyExecutedError, and the external action is dispatched exactly once.
  2. Replay prevention: Calling execute_approved on an already-executed approval raises
     ApprovalAlreadyExecutedError.
  3. Mid-execution crash reconciliation: If external dispatch raises an exception mid-call,
     the record remains in 'executing' state (never silently reverts to pending/approved),
     preventing duplicate dispatch and allowing reconciliation detection.
"""

import concurrent.futures
import threading
import time
from unittest.mock import patch

import pytest

from orchestrator_core.core.approval_gate import (
    approve,
    execute_approved,
    request_approval,
)
from orchestrator_core.exceptions import (
    ApprovalAlreadyExecutedError,
    ApprovalClaimConflictError,
    ApprovalNotGrantedError,
)
from orchestrator_core.storage.db import get_db, run_migrations


@pytest.fixture()
def shared_db(tmp_path):
    """File-backed SQLite DB with WAL mode so multiple threads can interact concurrently."""
    db_file = str(tmp_path / "concurrent_approvals.db")
    init_conn = get_db(db_file)
    run_migrations(init_conn)
    init_conn.close()
    return db_file


def test_concurrent_approve_single_claim(shared_db):
    """
    Two concurrent threads call execute_approved on the same approval_id.
    Exactly one succeeds; the other fails. The action is dispatched exactly once.
    """
    # 1. Setup row in approved state
    setup_conn = get_db(shared_db)
    aid = request_approval("publish_hashnode", {"title": "Concurrent Post"}, setup_conn)
    approve(aid, setup_conn)
    setup_conn.close()

    dispatch_calls = 0
    dispatch_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def slow_dispatch(*args, **kwargs):
        nonlocal dispatch_calls
        with dispatch_lock:
            dispatch_calls += 1
        # Sleep slightly to widen race window
        time.sleep(0.05)

    results = []
    exceptions = []

    def worker():
        conn = get_db(shared_db)
        try:
            # Synchronize thread start
            barrier.wait(timeout=2.0)
            execute_approved(aid, conn)
            results.append("success")
        except Exception as exc:
            exceptions.append(exc)
        finally:
            conn.close()

    with patch("orchestrator_core.core.approval_gate._dispatch_action", side_effect=slow_dispatch):
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

    # Exactly one thread must have succeeded
    assert len(results) == 1, f"Expected exactly 1 success, got {len(results)}"
    assert len(exceptions) == 1, f"Expected exactly 1 exception, got {len(exceptions)}"
    assert isinstance(
        exceptions[0],
        (ApprovalClaimConflictError, ApprovalAlreadyExecutedError, ApprovalNotGrantedError),
    )
    # The external dispatch must have run exactly once
    assert dispatch_calls == 1


def test_replay_after_execution_raises(db):
    """Calling execute_approved() on an already executed row raises ApprovalAlreadyExecutedError."""
    aid = request_approval("send_email", {"to": "aaqil@example.com"}, db)
    approve(aid, db)
    execute_approved(aid, db)

    with pytest.raises(ApprovalAlreadyExecutedError):
        execute_approved(aid, db)


def test_restart_mid_execution_reconciliation(db):
    """
    If dispatch fails or process crashes mid-execution, the approval row
    remains in 'executing' status. It cannot be re-executed by normal calls,
    and can be detected by reconciliation queries.
    """
    aid = request_approval("publish_devto", {"title": "Crash Test"}, db)
    approve(aid, db)

    class SimulatedCrashError(Exception):
        pass

    with patch(
        "orchestrator_core.core.approval_gate._dispatch_action",
        side_effect=SimulatedCrashError("Network timeout during publish"),
    ):
        with pytest.raises(SimulatedCrashError):
            execute_approved(aid, db)

    # Verify status is still 'executing', not reverted to pending or marked executed
    row = db.execute("SELECT status, executed_at FROM approvals WHERE id = ?", (aid,)).fetchone()
    assert row["status"] == "executing"
    assert row["executed_at"] is None

    # Normal re-execution must be blocked because status != 'approved'
    with pytest.raises(ApprovalNotGrantedError):
        execute_approved(aid, db)

    # Reconciliation query finds the stuck executing row
    stuck_rows = db.execute(
        "SELECT id, action_type FROM approvals WHERE status = 'executing'"
    ).fetchall()
    stuck_ids = [r["id"] for r in stuck_rows]
    assert aid in stuck_ids
