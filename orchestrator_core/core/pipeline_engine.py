"""
orchestrator_core/core/pipeline_engine.py

Step executor for named pipelines.

Each pipeline step is wrapped to:
  - Record a pipeline_steps row (agent_name, input_json, output_json, latency_ms, success, timestamp)
  - Propagate run_id through every step
  - Write the pipeline_runs row on start and update on completion/failure

Supported pipelines:
  - research  — research_agent
  - apply     — career_agent (absorbs cover-letter per corrective plan §2.1)
  - publish   — growth_content_agent → approval gate (never direct SDK)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from orchestrator_core.models import PipelineRequest

logger = logging.getLogger(__name__)


def _write_step(
    db: sqlite3.Connection,
    run_id: str,
    step_number: int,
    agent_name: str,
    input_data: Any,
    output_data: Any,
    latency_ms: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Write a single pipeline step record to the database."""
    with db:
        db.execute(
            """
            INSERT INTO pipeline_steps
                (run_id, step_number, agent_name, input_json, output_json, latency_ms, success, timestamp, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                step_number,
                agent_name,
                json.dumps(input_data, default=str),
                json.dumps(output_data, default=str),
                latency_ms,
                success,
                datetime.now(timezone.utc).isoformat(),
                error,
            ),
        )


def _run_step(
    db: sqlite3.Connection,
    run_id: str,
    step_number: int,
    agent_name: str,
    command: str,
    handler,
) -> dict[str, Any]:
    """Execute one agent step, record it, and return the result dict."""
    t0 = time.monotonic()
    try:
        result = handler(command, metadata={"run_id": run_id, "step": step_number})
        latency_ms = int((time.monotonic() - t0) * 1000)
        _write_step(db, run_id, step_number, agent_name, {"command": command},
                    {"output": result.output, "metadata": result.metadata},
                    latency_ms, True)
        return {"success": True, "result": result}
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        _write_step(db, run_id, step_number, agent_name, {"command": command},
                    {"error": str(exc)}, latency_ms, False, str(exc))
        raise


def run_pipeline(
    pipeline_name: str,
    request: PipelineRequest,
    db: sqlite3.Connection,
) -> str:
    """
    Execute a named pipeline. Returns the run_id.

    Writes a pipeline_runs row on start, updates status on completion or failure.
    Every agent step is recorded in pipeline_steps.
    """
    from orchestrator_core.agents import career_agent, research_agent, growth_content_agent

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    # Create the run record
    with db:
        db.execute(
            """
            INSERT INTO pipeline_runs (run_id, pipeline_name, command, status, started_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (run_id, pipeline_name, request.command, started_at),
        )

    logger.info("Pipeline start — run_id=%s name=%s command=%.60s", run_id, pipeline_name, request.command)

    try:
        if pipeline_name == "research":
            _run_step(db, run_id, 1, "research_agent", request.command, research_agent.handle)

        elif pipeline_name == "apply":
            # Career agent handles cover letters + tailoring (absorbed from JobAgent)
            _run_step(db, run_id, 1, "career_agent", request.command, career_agent.handle)

        elif pipeline_name == "publish":
            # Growth agent generates content — never publishes directly
            step_out = _run_step(db, run_id, 1, "growth_content_agent", request.command, growth_content_agent.handle)
            res = step_out.get("result")
            if res and getattr(res, "action_type", None):
                from orchestrator_core.core.approval_gate import request_approval
                request_approval(
                    action_type=res.action_type,
                    payload={"command": request.command, "content": res.output, "run_id": run_id},
                    db=db,
                )

        else:
            raise ValueError(f"Unknown pipeline: {pipeline_name!r}. Supported: research, apply, publish")

        # Mark completed
        with db:
            db.execute(
                "UPDATE pipeline_runs SET status = 'completed', completed_at = ? WHERE run_id = ?",
                (datetime.now(timezone.utc).isoformat(), run_id),
            )
        logger.info("Pipeline complete — run_id=%s", run_id)

    except Exception as exc:
        with db:
            db.execute(
                "UPDATE pipeline_runs SET status = 'failed', completed_at = ?, error = ? WHERE run_id = ?",
                (datetime.now(timezone.utc).isoformat(), str(exc), run_id),
            )
        logger.exception("Pipeline failed — run_id=%s", run_id)
        raise

    return run_id
