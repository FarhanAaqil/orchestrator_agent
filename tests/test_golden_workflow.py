"""
tests/test_golden_workflow.py

End-to-end integration and golden workflow testing for Phase 5 Autonomy Engine:
  1. Multi-step ReAct Golden Workflow (Research -> Draft -> Propose Approval -> Approve/Execute -> Final Succeeded)
  2. Crash Resumption Verification (Resuming execution seamlessly from SQLite checkpoints)
  3. HTTP REST & SSE Endpoints for /jobs and /system
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from orchestrator_core.core.approval_gate import approve, execute_approved
from orchestrator_core.jobs.service import JobService
from orchestrator_core.main import app
from orchestrator_core.models import JobRecord
from orchestrator_core.runner.loop import run_job
from orchestrator_core.storage.db import get_db, run_migrations


@pytest.fixture
def clean_db(tmp_path) -> sqlite3.Connection:
    """Fixture providing a fresh isolated SQLite database with migrations."""
    db_file = str(tmp_path / "test_golden.db")
    conn = get_db(db_file)
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(clean_db: sqlite3.Connection) -> TestClient:
    """FastAPI TestClient using clean_db via FastAPI dependency_overrides."""
    from orchestrator_core.storage.db import get_db_connection

    app.dependency_overrides[get_db_connection] = lambda: clean_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Golden Workflow: Research -> Draft -> Propose -> Approve -> Finish ─────────

def test_golden_workflow_end_to_end(clean_db: sqlite3.Connection):
    """
    Execute complete autonomous golden workflow:
      Turn 1: Agent calls search tool.
      Turn 2: Agent proposes publication (transitions to awaiting_approval).
      Human: Approves and executes approval proposal.
      Turn 3: Agent resumes and produces final synthesis artifact (transitions to succeeded).
    """
    job = JobService.create_job(
        agent="orchestrator",
        goal="Research multi-agent fault tolerance and publish summary article",
        db=clean_db,
    )
    assert job.status == "queued"

    # Step 1: Claim job
    job = JobService.claim_job("worker-alpha", clean_db)
    assert job is not None
    assert job.status == "running"

    # Turn sequence generator for MockLLM
    turns = [
        # Turn 1: tool call
        json.dumps({
            "thought": "I need to search for papers on agent fault tolerance.",
            "action": "tool_call",
            "action_input": {"name": "search_arxiv", "args": {"topic": "fault tolerance"}},
        }),
        # Turn 2: propose article publication
        json.dumps({
            "thought": "Research collected. Proposing publication to Dev.to.",
            "action": "propose",
            "action_input": {
                "action_type": "publish_devto",
                "payload": {
                    "title": "Fault Tolerance in Agentic AI",
                    "content": "Comprehensive analysis of state machines...",
                },
                "target": "devto",
            },
        }),
    ]

    mock_llm = MagicMock(side_effect=lambda msgs: turns.pop(0) if turns else json.dumps({
        "thought": "Publication was approved and executed. I will finalize the job.",
        "action": "final",
        "action_input": {"summary": "Article successfully published on Dev.to."},
    }))

    # Custom tool registry providing search_arxiv
    def mock_search_arxiv(topic: str) -> str:
        return f"Found 3 relevant papers for topic: {topic}"

    tools = {"search_arxiv": mock_search_arxiv}

    # Run loop (Phase A: executes Turn 1, then Turn 2 which pauses in awaiting_approval)
    paused_job = run_job(
        job=job,
        db=clean_db,
        llm_client=mock_llm,
        worker_id="worker-alpha",
        tool_registry=tools,
    )

    assert paused_job.status == "awaiting_approval"
    steps = JobService.get_steps(job.id, clean_db)
    # Step 0: LLM thought 1
    # Step 1: Tool execution
    # Step 2: LLM thought 2
    # Step 3: Propose approval
    assert len(steps) >= 4
    propose_step = next(s for s in steps if s.kind == "propose")
    prop_data = json.loads(propose_step.output_json)
    approval_id = prop_data["approval_id"]

    # Phase B: Human review and approval execution via approval gate
    approve(approval_id, clean_db)
    row_appr = clean_db.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    assert row_appr["status"] == "approved"

    # Execute approved action with mock SDK
    with patch("orchestrator_core.core.approval_gate._dispatch_action") as mock_dispatch:
        mock_dispatch.return_value = {"url": "https://dev.to/aaqil/fault-tolerance", "status": "published"}
        execute_approved(approval_id, db=clean_db)
        row_exec = clean_db.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        assert row_exec["status"] == "executed"

    # Re-queue / resume job now that approval has been handled
    JobService.transition(job.id, "queued", clean_db)
    claimed_again = JobService.claim_job("worker-alpha", clean_db)
    assert claimed_again is not None

    # Run loop (Phase C: Turn 3 finalization)
    final_job = run_job(
        job=claimed_again,
        db=clean_db,
        llm_client=mock_llm,
        worker_id="worker-alpha",
        tool_registry=tools,
    )

    assert final_job.status == "succeeded"
    assert final_job.result_json is not None
    assert "Article successfully published on Dev.to" in final_job.result_json


# ── Crash Resumption Verification ─────────────────────────────────────────────

def test_crash_resumption_from_checkpoints(clean_db: sqlite3.Connection):
    """
    Test that if Worker 1 crashes midway through execution, Worker 2
    picks up from the persistent SQLite step checkpoints without loss of context.
    """
    job = JobService.create_job(
        agent="writer",
        goal="Draft blog post with outline and body",
        db=clean_db,
    )
    claimed_1 = JobService.claim_job("worker-1", clean_db)
    assert claimed_1 is not None

    # Worker 1 takes 1 step (tool_call) then crashes/terminates
    worker_1_turn = json.dumps({
        "thought": "I will create the blog outline first.",
        "action": "tool_call",
        "action_input": {"name": "generate_outline", "args": {"theme": "autonomous agents"}},
    })

    def outline_tool(theme: str) -> str:
        return f"Outline for {theme}: 1. Intro, 2. Architecture, 3. Conclusion"

    tools = {"generate_outline": outline_tool}

    # Worker 1 executes step 0 (llm) and step 1 (tool)
    # Then we simulate crash by exiting runner (raising StopIteration or simply stopping)
    try:
        def crashing_llm(msgs):
            if len(msgs) > 2:  # After first turn
                raise RuntimeError("Simulated worker process crash / OOM!")
            return worker_1_turn

        run_job(job=claimed_1, db=clean_db, llm_client=crashing_llm, worker_id="worker-1", tool_registry=tools)
    except Exception:
        pass

    # Verify step checkpoints exist in DB
    steps_after_crash = JobService.get_steps(job.id, clean_db)
    assert len(steps_after_crash) >= 2
    assert any(s.name == "generate_outline" for s in steps_after_crash)

    # Re-queue job (as would happen via zombie reaper)
    with clean_db:
        clean_db.execute("UPDATE jobs SET status = 'queued', claimed_by = NULL WHERE id = ?", (job.id,))

    # Worker 2 claims the job
    claimed_2 = JobService.claim_job("worker-2", clean_db)
    assert claimed_2 is not None

    # Worker 2 should receive the previous outline observation in its prompt and finish
    received_prompts = []

    def worker_2_llm(msgs):
        received_prompts.append(msgs)
        return json.dumps({
            "thought": "I see the existing outline from prior step. Completing final draft.",
            "action": "final",
            "action_input": {"summary": "Full draft created based on outline."},
        })

    completed_job = run_job(
        job=claimed_2,
        db=clean_db,
        llm_client=worker_2_llm,
        worker_id="worker-2",
        tool_registry=tools,
    )

    assert completed_job.status == "succeeded"
    assert "Full draft created based on outline" in completed_job.result_json

    # Verify context sent to Worker 2 contained the observation from Worker 1
    last_context = received_prompts[0]
    flat_context = " ".join(m.get("content", "") for m in last_context)
    assert "Outline for autonomous agents" in flat_context


# ── HTTP API Integration Tests ────────────────────────────────────────────────

def test_api_jobs_crud_and_controls(client: TestClient):
    """Verify HTTP endpoints for creating, retrieving, listing, and cancelling jobs."""
    # 1. Create Job (POST /jobs)
    payload = {
        "agent": "research",
        "goal": "Test job creation via REST API",
        "params": {"query": "vector databases"},
        "priority": 3,
        "max_steps": 15,
        "token_budget": 30000,
    }
    resp = client.post("/jobs", json=payload)
    assert resp.status_code == 201
    created = resp.json()
    job_id = created["id"]
    assert created["agent"] == "research"
    assert created["status"] == "queued"
    assert created["priority"] == 3

    # 2. Get Job (GET /jobs/{id})
    get_resp = client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id

    # 3. List Jobs (GET /jobs)
    list_resp = client.get("/jobs?agent=research")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(j["id"] == job_id for j in list_data["items"])

    # 4. Get Job Steps (GET /jobs/{id}/steps)
    steps_resp = client.get(f"/jobs/{job_id}/steps")
    assert steps_resp.status_code == 200
    assert isinstance(steps_resp.json(), list)

    # 5. Cancel Job (POST /jobs/{id}/cancel)
    cancel_resp = client.post(f"/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_api_system_controls(client: TestClient):
    """Verify kill switch, system flags, and daily budget endpoints."""
    # 1. Toggle kill switch ON
    ks_on = client.post("/system/kill-switch", json={"on": True})
    assert ks_on.status_code == 200
    assert ks_on.json()["kill_switch"] == "on"

    # 2. Inspect flags (GET /system/flags)
    flags_resp = client.get("/system/flags")
    assert flags_resp.status_code == 200
    flags = {f["key"]: f["value"] for f in flags_resp.json()}
    assert flags.get("kill_switch") == "on"

    # 3. Set daily budget (POST /system/budget)
    budget_resp = client.post("/system/budget", json={"daily_budget_usd": 25.50})
    assert budget_resp.status_code == 200
    assert budget_resp.json()["daily_budget_usd"] == 25.50

    # 4. Toggle kill switch back OFF
    ks_off = client.post("/system/kill-switch", json={"on": False})
    assert ks_off.status_code == 200
    assert ks_off.json()["kill_switch"] == "off"
