"""
tests/test_publish_pipeline_integration.py

End-to-end integration test for the publish pipeline and approval gate.

CONTRACT UNDER TEST:
  1. The publish pipeline invokes growth_content_agent to draft content.
  2. If the user requested publishing, the pipeline queues an approval row (pending).
  3. The publishing SDK is NEVER called during pipeline execution.
  4. Unapproved or rejected requests cannot trigger SDK dispatch.
  5. Only explicit approve() followed by execute_approved() triggers SDK dispatch.
  6. The SDK is called strictly with the canonical payload saved during pipeline execution.
"""

from unittest.mock import MagicMock, patch
import pytest

from orchestrator_core.core.approval_gate import (
    approve,
    execute_approved,
    reject,
)
from orchestrator_core.core.pipeline_engine import run_pipeline
from orchestrator_core.exceptions import (
    ApprovalAlreadyExecutedError,
    ApprovalNotGrantedError,
)
from orchestrator_core.models import PipelineRequest


def test_publish_pipeline_end_to_end_approval_flow(db):
    """
    Full pipeline run:
    1. Pipeline runs and generates blog content.
    2. Approval row queued in 'pending' status.
    3. Mock SDK dispatch is NOT called during pipeline run.
    4. Premature execution fails.
    5. Approval granted, execute_approved claims and dispatches SDK.
    6. Double execution blocked.
    """
    fake_content = "# Agent Architecture\nBuilding robust autonomous systems."

    with patch("orchestrator_core.agents.growth_content_agent._call_llm", return_value=fake_content):
        with patch("orchestrator_core.core.approval_gate._dispatch_action") as mock_dispatch:
            # Step 1: Run publish pipeline
            req = PipelineRequest(command="Publish blog post to hashnode about autonomous agents")
            run_id = run_pipeline("publish", req, db)

            assert run_id is not None

            # Verify pipeline run recorded
            run_row = db.execute("SELECT status FROM pipeline_runs WHERE run_id = ?", (run_id,)).fetchone()
            assert run_row["status"] == "completed"

            # Verify pipeline step recorded
            step_row = db.execute("SELECT agent_name, success FROM pipeline_steps WHERE run_id = ?", (run_id,)).fetchone()
            assert step_row["agent_name"] == "growth_content_agent"
            assert bool(step_row["success"]) is True

            # Crucial assertion: SDK dispatch was NOT called during pipeline execution
            mock_dispatch.assert_not_called()

            # Verify approval row was queued
            approval_row = db.execute(
                "SELECT id, action_type, payload_json, status FROM approvals WHERE action_type = 'publish_hashnode'"
            ).fetchone()
            assert approval_row is not None
            assert approval_row["status"] == "pending"
            aid = approval_row["id"]

            # Step 2: Attempt execute before human approval -> MUST raise
            with pytest.raises(ApprovalNotGrantedError):
                execute_approved(aid, db)
            mock_dispatch.assert_not_called()

            # Step 3: Human approves
            approve(aid, db)
            mock_dispatch.assert_not_called()

            # Step 4: Execute approved
            execute_approved(aid, db)
            assert mock_dispatch.call_count == 1
            call_kwargs = mock_dispatch.call_args.kwargs
            assert call_kwargs["action_type"] == "publish_hashnode"
            assert call_kwargs["payload"]["run_id"] == run_id
            assert call_kwargs["payload"]["content"] == fake_content

            # Step 5: Verify status is executed
            updated_row = db.execute("SELECT status, executed_at FROM approvals WHERE id = ?", (aid,)).fetchone()
            assert updated_row["status"] == "executed"
            assert updated_row["executed_at"] is not None

            # Step 6: Replay attempt blocked
            with pytest.raises(ApprovalAlreadyExecutedError):
                execute_approved(aid, db)
            assert mock_dispatch.call_count == 1


def test_publish_pipeline_draft_only_no_approval_queued(db):
    """
    If the user only asks to write/draft without publish intent,
    the pipeline completes successfully but NO approval row is created.
    """
    with patch("orchestrator_core.agents.growth_content_agent._call_llm", return_value="Draft text"):
        with patch("orchestrator_core.core.approval_gate._dispatch_action") as mock_dispatch:
            req = PipelineRequest(command="Draft a tech article about Python typing")
            run_id = run_pipeline("publish", req, db)

            assert run_id is not None
            mock_dispatch.assert_not_called()

            # Verify no approvals queued
            count = db.execute("SELECT COUNT(*) as cnt FROM approvals").fetchone()["cnt"]
            assert count == 0
