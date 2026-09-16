"""
orchestrator_core/routes/pipeline.py

Pipeline execution HTTP routes.

  POST /pipeline/{name}  — execute a named pipeline (apply, publish, research)
                           Returns the run_id for async polling via GET /runs/{id}
"""

import logging
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from orchestrator_core.storage.db import get_db_connection
from orchestrator_core.core.pipeline_engine import run_pipeline
from orchestrator_core.models import PipelineRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["Pipelines"])

SUPPORTED_PIPELINES = ["apply", "publish", "research"]


class PipelineStarted(BaseModel):
    run_id: str
    pipeline_name: str
    status: str = "running"


@router.post("/{pipeline_name}", response_model=PipelineStarted)
async def start_pipeline(
    pipeline_name: str,
    body: PipelineRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """
    Execute a named pipeline synchronously and return the run_id.

    Poll GET /runs/{run_id} to retrieve the full step-by-step trace.
    """
    if pipeline_name not in SUPPORTED_PIPELINES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Unknown pipeline '{pipeline_name}'. Supported: {SUPPORTED_PIPELINES}",
        )

    run_id = run_pipeline(pipeline_name, body, db)
    return PipelineStarted(run_id=run_id, pipeline_name=pipeline_name, status="completed")
