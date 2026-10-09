"""
tests/test_agent_golden_workflows.py

Golden workflow test suites for specialized autonomous agents (Phase 6):
  1. research_agent: arxiv_search -> fetch_page -> final synthesis
  2. github_agent: github_read -> propose_action -> human approval -> final completion
  3. email_agent: email_read -> propose_action -> human approval -> final completion
  4. critic_agent: zero tools allowed -> pure rubric evaluation -> final output
  5. Enforcement: Runner loop blocks calls to non-allowlisted tools with security observation
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch
import pytest

from orchestrator_core.core.approval_gate import approve, execute_approved
from orchestrator_core.jobs.service import JobService
from orchestrator_core.runner.loop import run_job
from orchestrator_core.storage.db import get_db, run_migrations


@pytest.fixture
def clean_db(tmp_path) -> sqlite3.Connection:
    """Provide an isolated SQLite database with schema migrations."""
    db_file = str(tmp_path / "test_agents.db")
    conn = get_db(db_file)
    run_migrations(conn)
    yield conn
    conn.close()


def test_research_agent_golden_workflow(clean_db: sqlite3.Connection):
    """
    Research agent workflow:
      Turn 1: Calls arxiv_search.
      Turn 2: Finalizes literature synthesis.
    """
    job = JobService.create_job(
        agent="research_agent",
        goal="Survey recent papers on state machine verification in AI agents",
        db=clean_db,
    )
    job = JobService.claim_job("worker-r1", clean_db)
    assert job is not None

    turns = [
        json.dumps({
            "thought": "I should search arXiv for recent state machine papers.",
            "action": "tool_call",
            "action_input": {
                "name": "arxiv_search",
                "args": {"query": "state machine verification agents", "max_results": 2},
            },
        }),
        json.dumps({
            "thought": "I have collected the relevant literature. Formulating survey.",
            "action": "final",
            "action_input": {"summary": "Identified key advances in formal verification for LLM agents."},
        }),
    ]

    mock_llm = MagicMock(side_effect=lambda msgs: turns.pop(0))

    with patch("orchestrator_core.tools.read.arxiv_search.safe_get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Formal Verification of Agentic State Machines</title>
            <summary>We present a verified model for autonomous agents...</summary>
            <id>http://arxiv.org/abs/2601.12345v1</id>
            <published>2026-01-15T00:00:00Z</published>
            <author><name>Alice Doe</name></author>
          </entry>
        </feed>
        """
        mock_get.return_value = mock_resp

        finished_job = run_job(job, clean_db, llm_client=mock_llm, worker_id="worker-r1")

    assert finished_job.status == "succeeded"
    assert finished_job.result_json is not None
    assert "Identified key advances" in finished_job.result_json


def test_github_agent_golden_workflow(clean_db: sqlite3.Connection):
    """
    GitHub agent workflow:
      Turn 1: Calls github_read to inspect repo issues.
      Turn 2: Proposes creating an issue via propose_action tool call.
      Human: Approves & executes proposal.
      Turn 3: Resumes and finalizes.
    """
    job = JobService.create_job(
        agent="github_agent",
        goal="Inspect repo issues and propose bug report for zombie reapers",
        db=clean_db,
    )
    job = JobService.claim_job("worker-gh", clean_db)
    assert job is not None

    turn1 = json.dumps({
        "thought": "I will inspect repository issues first.",
        "action": "tool_call",
        "action_input": {
            "name": "github_read",
            "args": {"action": "list_issues", "repo": "FarhanAaqil/orchestrater_agent"},
        },
    })
    turn2 = json.dumps({
        "thought": "Issue verified. Proposing bug report issue creation.",
        "action": "tool_call",
        "action_input": {
            "name": "propose_action",
            "args": {
                "action_type": "github_issue",
                "target": "FarhanAaqil/orchestrater_agent",
                "payload": {
                    "title": "Bug: Zombie worker heartbeat race condition",
                    "body": "Need heartbeat refresh before reaping.",
                },
            },
        },
    })

    turns = [turn1, turn2]
    mock_llm = MagicMock(side_effect=lambda msgs: turns.pop(0) if turns else json.dumps({
        "thought": "Issue was approved and executed. Finalizing task.",
        "action": "final",
        "action_input": {"summary": "GitHub issue creation proposed and completed."},
    }))

    with patch("orchestrator_core.tools.read.github_read.safe_get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"number": 1, "title": "Initial commit", "state": "open"}]
        mock_get.return_value = mock_resp

        # Turn 1 and 2 run until awaiting_approval
        paused_job = run_job(job, clean_db, llm_client=mock_llm, worker_id="worker-gh")

    assert paused_job.status == "awaiting_approval"

    # Extract approval ID from recorded propose step
    steps = JobService.get_steps(job.id, clean_db)
    propose_step = next(s for s in steps if s.kind == "propose")
    prop_data = json.loads(propose_step.output_json)
    approval_id = prop_data["approval_id"]
    assert approval_id is not None

    # Human approves and executes
    with patch("orchestrator_core.core.approval_gate._dispatch_action") as mock_dispatch:
        mock_dispatch.return_value = None
        approve(approval_id, db=clean_db)
        execute_approved(approval_id, db=clean_db)

    # Re-queue and resume job execution
    JobService.transition(job.id, "queued", clean_db)
    resumed_job = JobService.claim_job("worker-gh", clean_db)
    assert resumed_job is not None

    final_job = run_job(resumed_job, clean_db, llm_client=mock_llm, worker_id="worker-gh")

    assert final_job.status == "succeeded"
    assert final_job.result_json is not None
    assert "GitHub issue creation proposed and completed." in final_job.result_json


def test_email_agent_golden_workflow(clean_db: sqlite3.Connection):
    """
    Email agent workflow:
      Turn 1: Calls email_read to check inbox.
      Turn 2: Calls propose_action to stage recruiter reply.
      Human: Approves & executes proposal.
      Turn 3: Resumes and finalizes.
    """
    job = JobService.create_job(
        agent="email_agent",
        goal="Check inbox for recruiter messages and draft response",
        db=clean_db,
    )
    job = JobService.claim_job("worker-mail", clean_db)
    assert job is not None

    turn1 = json.dumps({
        "thought": "Checking inbox for unread recruiter messages.",
        "action": "tool_call",
        "action_input": {
            "name": "email_read",
            "args": {"action": "check_inbox", "max_messages": 2},
        },
    })
    turn2 = json.dumps({
        "thought": "Recruiter message found. Staging response email.",
        "action": "tool_call",
        "action_input": {
            "name": "propose_action",
            "args": {
                "action_type": "send_email",
                "target": "recruiter@techcorp.example",
                "payload": {
                    "to": "recruiter@techcorp.example",
                    "subject": "Re: Senior AI Engineer Role - Farhan Aaqil",
                    "body": "Thank you for reaching out. I would be glad to discuss...",
                },
            },
        },
    })

    turns = [turn1, turn2]
    mock_llm = MagicMock(side_effect=lambda msgs: turns.pop(0) if turns else json.dumps({
        "thought": "Email response approved and dispatched.",
        "action": "final",
        "action_input": {"summary": "Recruiter reply staged, approved, and dispatched."},
    }))

    paused_job = run_job(job, clean_db, llm_client=mock_llm, worker_id="worker-mail")

    assert paused_job.status == "awaiting_approval"

    # Extract approval ID from recorded propose step
    steps = JobService.get_steps(job.id, clean_db)
    propose_step = next(s for s in steps if s.kind == "propose")
    prop_data = json.loads(propose_step.output_json)
    approval_id = prop_data["approval_id"]
    assert approval_id is not None

    with patch("orchestrator_core.core.approval_gate._dispatch_action") as mock_dispatch:
        mock_dispatch.return_value = None
        approve(approval_id, db=clean_db)
        execute_approved(approval_id, db=clean_db)

    # Re-queue and resume job
    JobService.transition(job.id, "queued", clean_db)
    resumed_job = JobService.claim_job("worker-mail", clean_db)
    assert resumed_job is not None

    final_job = run_job(resumed_job, clean_db, llm_client=mock_llm, worker_id="worker-mail")

    assert final_job.status == "succeeded"
    assert final_job.result_json is not None
    assert "dispatched" in final_job.result_json


def test_critic_agent_zero_tools_allowed(clean_db: sqlite3.Connection):
    """
    Critic agent workflow:
      Critic agent has zero allowed tools. Must evaluate input directly and return final score.
    """
    job = JobService.create_job(
        agent="critic_agent",
        goal="Audit security boundaries of the approval gate implementation",
        db=clean_db,
    )
    job = JobService.claim_job("worker-critic", clean_db)
    assert job is not None

    # Critic produces immediate final evaluation without calling external tools
    mock_llm = MagicMock(return_value=json.dumps({
        "thought": "I will perform rubric evaluation directly without external tools.",
        "action": "final",
        "action_input": {
            "summary": "Score: 9.5. Atomic CAS locking and zero payload substitution pass audit.",
        },
    }))

    final_job = run_job(job, clean_db, llm_client=mock_llm, worker_id="worker-critic")
    assert final_job.status == "succeeded"
    assert final_job.result_json is not None
    assert "9.5" in final_job.result_json


def test_unauthorized_tool_call_rejected_by_runner(clean_db: sqlite3.Connection):
    """
    Security check: If an agent attempts to invoke a tool that is not in its
    allowlist, the runner rejects it with an observation and does NOT execute the tool.
    """
    job = JobService.create_job(
        agent="critic_agent",  # Critic has frozenset() tools
        goal="Attempt unauthorized tool invocation",
        db=clean_db,
    )
    job = JobService.claim_job("worker-bad", clean_db)
    assert job is not None

    turns = [
        # Attempting to call email_read with critic_agent
        json.dumps({
            "thought": "Trying to read emails",
            "action": "tool_call",
            "action_input": {"name": "email_read", "args": {}},
        }),
        # Next turn after observation rejection
        json.dumps({
            "thought": "Recognized tool is unauthorized. Exiting gracefully.",
            "action": "final",
            "action_input": {"summary": "Aborted unauthorized tool call."},
        }),
    ]

    mock_llm = MagicMock(side_effect=lambda msgs: turns.pop(0))

    final_job = run_job(job, clean_db, llm_client=mock_llm, worker_id="worker-bad")
    assert final_job.status == "succeeded"

    # Verify that the rejected observation was recorded in job_steps
    steps = JobService.get_steps(job.id, clean_db)
    assert any(s.kind == "tool" and "not authorized" in (s.output_json or "") for s in steps)
