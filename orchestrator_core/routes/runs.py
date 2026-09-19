"""
orchestrator_core/routes/runs.py

GET /runs/{run_id} — retrieve a pipeline execution run with all its recorded steps.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
import sqlite3
from pydantic import BaseModel

from orchestrator_core.storage.db import get_db_connection
from orchestrator_core.models import PipelineRunStatus, PipelineStepRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["Pipeline Runs"])


class RunSummary(BaseModel):
    run_id: str
    pipeline_name: str
    command: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class RunListResponse(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


@router.get("", response_model=RunListResponse)
async def list_runs(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """List pipeline execution runs with optional status filter and bounded pagination."""
    if status:
        rows = db.execute(
            "SELECT run_id, pipeline_name, command, status, started_at, completed_at, error "
            "FROM pipeline_runs WHERE status = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        ).fetchall()
        total = db.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status = ?", (status,)
        ).fetchone()[0]
    else:
        rows = db.execute(
            "SELECT run_id, pipeline_name, command, status, started_at, completed_at, error "
            "FROM pipeline_runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]

    return RunListResponse(
        items=[
            RunSummary(
                run_id=r["run_id"],
                pipeline_name=r["pipeline_name"],
                command=r["command"],
                status=r["status"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                error=r["error"],
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


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
