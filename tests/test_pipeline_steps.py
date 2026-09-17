"""
tests/test_pipeline_steps.py

Unit and integration tests for orchestrator_core/core/pipeline_engine.py.
Verifies that every pipeline run accurately creates pipeline_runs and pipeline_steps
database records with required audit fields (input_json, output_json, latency_ms, success, timestamps).
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from orchestrator_core.core.pipeline_engine import run_pipeline
from orchestrator_core.models import AgentResult, PipelineRequest


def test_pipeline_steps_recorded_on_research_success(db):
    mock_result = AgentResult(
        agent="research_agent",
        output="Found 3 relevant papers on neural operators.",
        metadata={"papers_found": 3},
    )

    with patch("orchestrator_core.agents.research_agent.handle", return_value=mock_result) as mock_handle:
        req = PipelineRequest(command="Research Fourier neural operators")
        run_id = run_pipeline("research", req, db)

        assert run_id is not None
        mock_handle.assert_called_once()

        # Verify pipeline_runs row
        run_row = db.execute("SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)).fetchone()
        assert run_row is not None
        assert run_row["pipeline_name"] == "research"
        assert run_row["status"] == "completed"
        assert run_row["error"] is None
        assert run_row["started_at"] is not None
        assert run_row["completed_at"] is not None

        # Verify pipeline_steps row
        steps = db.execute(
            "SELECT * FROM pipeline_steps WHERE run_id = ? ORDER BY step_number ASC",
            (run_id,),
        ).fetchall()
        assert len(steps) == 1
        step = steps[0]
        assert step["step_number"] == 1
        assert step["agent_name"] == "research_agent"
        assert bool(step["success"]) is True
        assert step["error"] is None
        assert step["latency_ms"] >= 0

        input_data = json.loads(step["input_json"])
        assert input_data == {"command": "Research Fourier neural operators"}

        output_data = json.loads(step["output_json"])
        assert output_data["output"] == "Found 3 relevant papers on neural operators."
        assert output_data["metadata"]["papers_found"] == 3


def test_pipeline_steps_recorded_on_apply_success(db):
    mock_result = AgentResult(
        agent="career_agent",
        output="Drafted tailored cover letter for AI Research Intern position.",
        metadata={"role": "AI Research Intern"},
    )

    with patch("orchestrator_core.agents.career_agent.handle", return_value=mock_result):
        req = PipelineRequest(command="Apply to AI Research Intern at DeepMind")
        run_id = run_pipeline("apply", req, db)

        step = db.execute(
            "SELECT * FROM pipeline_steps WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert step is not None
        assert step["agent_name"] == "career_agent"
        assert bool(step["success"]) is True


def test_pipeline_step_failure_records_error(db):
    with patch(
        "orchestrator_core.agents.research_agent.handle",
        side_effect=RuntimeError("External arXiv API timeout"),
    ):
        req = PipelineRequest(command="Search for recent LLM reasoning papers")
        with pytest.raises(RuntimeError) as exc_info:
            run_pipeline("research", req, db)

        assert "arXiv API timeout" in str(exc_info.value)

        # Verify run marked failed
        run_row = db.execute(
            "SELECT * FROM pipeline_runs WHERE command = ?", (req.command,)
        ).fetchone()
        assert run_row is not None
        assert run_row["status"] == "failed"
        assert "arXiv API timeout" in run_row["error"]

        # Verify step marked failure with error string
        step = db.execute(
            "SELECT * FROM pipeline_steps WHERE run_id = ?", (run_row["run_id"],)
        ).fetchone()
        assert step is not None
        assert bool(step["success"]) is False
        assert "arXiv API timeout" in step["error"]


def test_unknown_pipeline_raises_value_error(db):
    req = PipelineRequest(command="Perform magic task")
    with pytest.raises(ValueError) as exc_info:
        run_pipeline("nonexistent_pipeline", req, db)

    assert "Unknown pipeline" in str(exc_info.value)
