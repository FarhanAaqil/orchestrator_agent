"""
orchestrator_core/routes/runs.py

GET /runs/{run_id} — retrieve a pipeline execution run with all its recorded steps.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
import sqlite3

from orchestrator_core.storage.db import get_db_connection
from orchestrator_core.models import PipelineRunStatus, PipelineStepRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["Pipeline Runs"])


@router.get("/{run_id}", response_model=PipelineRunStatus)
async def get_run(run_id: str, db: sqlite3.Connection = Depends(get_db_connection)):
    """Return a pipeline run record with all steps ordered by step_number."""
    row = db.execute(
        "SELECT run_id, pipeline_name, command, status, started_at, completed_at, error "
        "FROM pipeline_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found.")

    step_rows = db.execute(
        "SELECT run_id, step_number, agent_name, input_json, output_json, "
        "latency_ms, success, timestamp, error "
        "FROM pipeline_steps WHERE run_id = ? ORDER BY step_number ASC",
        (run_id,),
    ).fetchall()

    steps = [
        PipelineStepRecord(
            run_id=r["run_id"],
            step_number=r["step_number"],
            agent_name=r["agent_name"],
            input_json=r["input_json"],
            output_json=r["output_json"],
            latency_ms=r["latency_ms"],
            success=bool(r["success"]),
            timestamp=r["timestamp"],
            error=r["error"],
        )
        for r in step_rows
    ]

    return PipelineRunStatus(
        run_id=row["run_id"],
        pipeline_name=row["pipeline_name"],
        status=row["status"],
        steps=steps,
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )
