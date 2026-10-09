"""
tests/test_agent_failure_modes.py

Phase 6 Advanced Requirements:
  1. Per-agent failure-mode tests (tool outages handled gracefully without crashing jobs).
  2. Circuit breakers guarding external tools (google_search_api, ddg_search_api, arxiv_search_api, github_read_api).
  3. Dynamic roster health indicator (GET /agents and GET /agents/{id}).
  4. Administrative enable/disable toggle (PATCH /agents/{id}).
  5. Enforcement preventing execution or creation of disabled agents.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
import requests

from orchestrator_core.exceptions import (
    AgentDisabledError,
    CircuitOpenError,
)
from orchestrator_core.jobs.service import JobService
from orchestrator_core.main import app
from orchestrator_core.runner.caps import check_guards
from orchestrator_core.runner.loop import run_job
from orchestrator_core.storage.db import get_db, get_db_connection, run_migrations
from orchestrator_core.tools.read.arxiv_search import _arxiv_breaker
from orchestrator_core.tools.read.ddg_search import _ddg_breaker, ddg_search
from orchestrator_core.tools.read.github_read import _github_breaker, github_read
from orchestrator_core.tools.read.google_search import _google_search_breaker
from orchestrator_core.tools.registry import ALL_TOOL_BREAKERS


@pytest.fixture
def clean_db(tmp_path) -> sqlite3.Connection:
    """Fixture providing an isolated SQLite database with migrations."""
    db_file = str(tmp_path / "test_failure_modes.db")
    conn = get_db(db_file)
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(clean_db: sqlite3.Connection) -> TestClient:
    """FastAPI TestClient with dependency overrides on clean_db."""
    app.dependency_overrides[get_db_connection] = lambda: clean_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_all_circuit_breakers():
    """Ensure all circuit breakers start and end tests in CLOSED state."""
    for breaker in ALL_TOOL_BREAKERS.values():
        breaker.reset()
    yield
    for breaker in ALL_TOOL_BREAKERS.values():
        breaker.reset()


# ── 1. Tool Outage Failure Modes ──────────────────────────────────────────────

def test_tool_outage_handled_gracefully_in_agent_loop(clean_db: sqlite3.Connection):
    """
    When an authorized tool fails (network error, timeout, 5xx), the runner loop
    must catch the exception, record the step with ok=False and sanitized output,
    and allow the agent to inspect the error and finish without crashing the worker.
    """
    job = JobService.create_job(
        agent="research_agent",
        goal="Find papers on neural symbolic reasoning",
        db=clean_db,
    )
    claimed_job = JobService.claim_job("worker-1", clean_db)
    assert claimed_job is not None

    turns = [
        # Turn 1: Try to invoke arxiv_search
        json.dumps({
            "thought": "I will search arXiv for papers.",
            "action": "tool_call",
            "action_input": {
                "name": "arxiv_search",
                "args": {"query": "neural symbolic", "max_results": 2},
            },
        }),
        # Turn 2: Receive error observation, finish gracefully
        json.dumps({
            "thought": "The tool encountered an outage. I will provide a fallback summary.",
            "action": "final",
            "action_input": {"summary": "Unable to query arXiv due to upstream service outage. Fallback ready."},
        }),
    ]

    mock_llm = MagicMock()
    mock_llm.side_effect = [
        (turn, 50, 20) for turn in turns
    ]

    # Simulate tool outage: tool raises network error during execution
    def _failing_arxiv(**kwargs):
        raise RuntimeError("Connection reset by peer: arxiv.org unreachable")

    failing_tools = {
        "arxiv_search": _failing_arxiv,
    }
    result_job = run_job(
        claimed_job,
        clean_db,
        llm_client=mock_llm,
        worker_id="worker-1",
        tool_registry=failing_tools,
    )

    assert result_job.status == "succeeded"

    steps = JobService.get_steps(job.id, clean_db)
    tool_step = next(s for s in steps if s.kind == "tool")
    assert tool_step.name == "arxiv_search"
    assert tool_step.ok is False
    assert "Connection reset by peer" in tool_step.output_json

    final_step = next(s for s in steps if s.name == "final" and s.kind == "note")
    assert final_step.ok is True


def test_github_tool_outage_handled_gracefully(clean_db: sqlite3.Connection):
    """
    GitHub API outage must be safely swallowed into observation without crashing the job.
    """
    job = JobService.create_job(
        agent="github_agent",
        goal="Inspect repos for FarhanAaqil",
        db=clean_db,
    )
    claimed_job = JobService.claim_job("worker-1", clean_db)
    assert claimed_job is not None

    turns = [
        json.dumps({
            "thought": "Querying GitHub API.",
            "action": "tool_call",
            "action_input": {
                "name": "github_read",
                "args": {"action": "list_repos", "username": "FarhanAaqil"},
            },
        }),
        json.dumps({
            "thought": "GitHub API timed out. Reporting status.",
            "action": "final",
            "action_input": {"summary": "GitHub service is temporarily degraded."},
        }),
    ]

    mock_llm = MagicMock()
    mock_llm.side_effect = [(turn, 40, 20) for turn in turns]

    def _failing_gh(**kwargs):
        raise requests.exceptions.Timeout("HTTPSConnectionPool: Read timed out")

    failing_tools = {
        "github_read": _failing_gh,
    }
    result_job = run_job(
        claimed_job,
        clean_db,
        llm_client=mock_llm,
        worker_id="worker-1",
        tool_registry=failing_tools,
    )

    assert result_job.status == "succeeded"
    steps = JobService.get_steps(job.id, clean_db)
    tool_step = next(s for s in steps if s.kind == "tool")
    assert tool_step.name == "github_read"
    assert tool_step.ok is False
    assert "timed out" in tool_step.output_json.lower()


# ── 2. Circuit Breaker Outage Verification ────────────────────────────────────

def test_arxiv_circuit_breaker_trips_after_three_failures():
    """
    Simulating 3 consecutive failures trips arxiv_search circuit breaker to OPEN.
    Subsequent calls raise CircuitOpenError or fail fast.
    """
    assert _arxiv_breaker.state == "CLOSED"

    def _failing_call():
        raise requests.exceptions.HTTPError("Arxiv 503 Service Unavailable")

    for _ in range(3):
        try:
            _arxiv_breaker.call(_failing_call)
        except Exception:
            pass

    assert _arxiv_breaker.state == "OPEN"
    assert not _arxiv_breaker.can_execute()

    # Next call fails fast without executing
    with pytest.raises(CircuitOpenError):
        _arxiv_breaker.call(lambda: "should not be called")


def test_github_circuit_breaker_trips_after_three_failures():
    """
    Simulating 3 consecutive network failures trips github_read circuit breaker to OPEN.
    """
    assert _github_breaker.state == "CLOSED"

    def _failing_gh():
        raise requests.exceptions.ConnectionError("Network unreachable")

    for _ in range(3):
        try:
            _github_breaker.call(_failing_gh)
        except Exception:
            pass

    assert _github_breaker.state == "OPEN"
    assert not _github_breaker.can_execute()

    with pytest.raises(CircuitOpenError):
        _github_breaker.call(lambda: "should not run")


def test_google_search_circuit_breaker_trips():
    """
    Verify google_search_api circuit breaker transitions to OPEN after 3 failures.
    """
    assert _google_search_breaker.state == "CLOSED"
    for _ in range(3):
        _google_search_breaker.record_failure()

    assert _google_search_breaker.state == "OPEN"
    assert not _google_search_breaker.can_execute()


def test_ddg_search_circuit_breaker_trips_and_serves_fallback():
    """
    When ddg_search circuit breaker is OPEN, ddg_search serves a fallback message without error.
    """
    assert _ddg_breaker.state == "CLOSED"
    for _ in range(3):
        _ddg_breaker.record_failure()

    assert _ddg_breaker.state == "OPEN"
    results = ddg_search("quantum computing")
    assert len(results) >= 1
    assert "Circuit Open" in results[0]["title"]


# ── 3. Dynamic Roster Health Indicator ────────────────────────────────────────

def test_dynamic_roster_health_degraded_when_breaker_open(client: TestClient):
    """
    GET /agents reflects:
      - 'healthy' by default for all agents.
      - 'degraded' for research_agent when arxiv_search circuit breaker is OPEN.
      - other agents without arxiv_search remain 'healthy'.
    """
    # 1. Baseline: all agents healthy
    resp = client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 9
    for a in agents:
        assert a["status"] == "healthy"
        assert a["is_active"] is True

    # 2. Trip arxiv_search circuit breaker
    _arxiv_breaker.state = "OPEN"

    resp_degraded = client.get("/agents")
    assert resp_degraded.status_code == 200
    agents_map = {a["id"]: a for a in resp_degraded.json()}

    assert agents_map["research_agent"]["status"] == "degraded"
    assert agents_map["research_agent"]["circuit_breakers"]["arxiv_search"] == "OPEN"

    # Agents not using arxiv_search are still healthy
    assert agents_map["critic_agent"]["status"] == "healthy"
    assert agents_map["email_agent"]["status"] == "healthy"
    assert agents_map["github_agent"]["status"] == "healthy"

    # Single agent endpoint reflects degraded health
    single_resp = client.get("/agents/research_agent")
    assert single_resp.status_code == 200
    assert single_resp.json()["status"] == "degraded"

    # 3. Reset breaker restores healthy status
    _arxiv_breaker.reset()
    resp_restored = client.get("/agents/research_agent")
    assert resp_restored.status_code == 200
    assert resp_restored.json()["status"] == "healthy"


# ── 4. Administrative Enable/Disable Toggle ───────────────────────────────────

def test_administrative_enable_disable_toggle(client: TestClient):
    """
    PATCH /agents/{id} toggles agent between active and disabled.
    Disabled state is persisted in system_flags and returned in GET /agents.
    """
    # Disable research agent
    patch_resp = client.patch("/agents/research_agent", json={"is_active": False})
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["is_active"] is False
    assert data["status"] == "disabled"

    # Verify GET reflects disabled state
    get_resp = client.get("/agents/research_agent")
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False
    assert get_resp.json()["status"] == "disabled"

    # Re-enable via alias 'research'
    patch_alias_resp = client.patch("/agents/research", json={"is_active": True})
    assert patch_alias_resp.status_code == 200
    assert patch_alias_resp.json()["is_active"] is True
    assert patch_alias_resp.json()["status"] == "healthy"


# ── 5. Enforcement Preventing Disabled Agent Execution ────────────────────────

def test_enforcement_blocks_job_creation_for_disabled_agent(
    clean_db: sqlite3.Connection,
    client: TestClient,
):
    """
    Creating a job for a disabled agent must be rejected:
      - JobService.create_job() raises AgentDisabledError
      - POST /jobs API returns 403 Forbidden with error='AGENT_DISABLED'
    """
    # Administratively disable career_agent
    client.patch("/agents/career_agent", json={"is_active": False})

    # Direct JobService call raises AgentDisabledError
    with pytest.raises(AgentDisabledError) as exc_info:
        JobService.create_job(
            agent="career_agent",
            goal="Review resume for ML role",
            db=clean_db,
        )
    assert "career_agent" in str(exc_info.value)

    # Calling with alias also raises AgentDisabledError
    with pytest.raises(AgentDisabledError):
        JobService.create_job(
            agent="career",
            goal="Review resume",
            db=clean_db,
        )

    # REST API POST /jobs returns 403 Forbidden
    api_resp = client.post(
        "/jobs",
        json={"agent": "career_agent", "goal": "Resume review via API"},
    )
    assert api_resp.status_code == 403
    assert api_resp.json()["error"] == "AGENT_DISABLED"


def test_enforcement_halts_running_job_when_agent_disabled(clean_db: sqlite3.Connection):
    """
    If an agent is disabled while a job is running or queued, check_guards()
    raises AgentDisabledError and the runner marks the job as 'failed'.
    """
    # 1. Create job while enabled
    JobService.create_job(
        agent="github_agent",
        goal="Audit repository commits",
        db=clean_db,
    )
    claimed = JobService.claim_job("worker-1", clean_db)
    assert claimed is not None

    # 2. Administratively disable github_agent
    with clean_db:
        clean_db.execute(
            "INSERT OR REPLACE INTO system_flags (key, value) VALUES ('agent_enabled_github_agent', '0')"
        )

    # 3. check_guards() raises AgentDisabledError
    with pytest.raises(AgentDisabledError):
        check_guards(claimed, clean_db)

    # 4. run_job() handles AgentDisabledError by transitioning job to failed
    result_job = run_job(claimed, clean_db, worker_id="worker-1")
    assert result_job.status == "failed"
    assert "administratively disabled" in (result_job.error or "").lower()


def test_enforcement_blocks_dispatch_for_disabled_agent(
    clean_db: sqlite3.Connection,
    client: TestClient,
):
    """
    POST /dispatch rejects execution with 403 if the routed agent is disabled.
    """
    # Disable email_agent
    client.patch("/agents/email_agent", json={"is_active": False})

    resp = client.post(
        "/dispatch",
        json={"command": "check my unread emails and inbox"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "AGENT_DISABLED"
