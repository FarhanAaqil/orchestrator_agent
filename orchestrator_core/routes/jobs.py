"""
orchestrator_core/routes/jobs.py

HTTP endpoints for managing persistent autonomous jobs, step history, and SSE events.

  GET  /jobs              — list jobs with filters and pagination
  POST /jobs              — create/enqueue a new autonomous job
  GET  /jobs/events       — stream real-time SSE job events
  GET  /jobs/{id}         — get job record by ID
  GET  /jobs/{id}/steps   — get chronological step trace for a job
  POST /jobs/{id}/cancel  — cancel a queued or running job
  POST /jobs/{id}/answer  — answer a pending user input question
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestrator_core.dependencies import verify_bearer_token
from orchestrator_core.exceptions import (
    InvalidJobStateTransitionError,
    JobNotFoundError,
)
from orchestrator_core.jobs.events import event_hub
from orchestrator_core.jobs.service import JobService
from orchestrator_core.models import (
    JobAnswerRequest,
    JobCreateRequest,
    JobRecord,
    JobStepRecord,
)
from orchestrator_core.storage.db import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobListResponse(BaseModel):
    items: list[JobRecord]
    total: int
    limit: int
    offset: int


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(default=None, description="Filter by job status"),
    agent: Optional[str] = Query(default=None, description="Filter by agent"),
    thread_id: Optional[str] = Query(default=None, description="Filter by thread_id"),
    session_id: Optional[str] = Query(default=None, description="Filter by session_id"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """List jobs with optional filters and pagination."""
    items, total = JobService.list_jobs(
        db=db,
        status=status,
        agent=agent,
        thread_id=thread_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return JobListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=JobRecord, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: JobCreateRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """Create and enqueue a new autonomous job."""
    return JobService.create_job(
        agent=request.agent,
        goal=request.goal,
        db=db,
        params=request.params,
        thread_id=request.thread_id,
        parent_job_id=request.parent_job_id,
        session_id=request.session_id,
        priority=request.priority,
        max_steps=request.max_steps,
        token_budget=request.token_budget,
    )


@router.get("/events")
async def stream_job_events(
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """
    SSE stream of real-time job state transitions, steps, and system notifications.
    """
    return StreamingResponse(
        event_hub.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}", response_model=JobRecord)
async def get_job(
    job_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """Fetch an autonomous job record by ID."""
    job = JobService.get_job(job_id, db)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return job


@router.get("/{job_id}/steps", response_model=list[JobStepRecord])
async def get_job_steps(
    job_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """Fetch chronological execution trace of steps for a job."""
    job = JobService.get_job(job_id, db)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return JobService.get_steps(job_id, db)


@router.post("/{job_id}/cancel", response_model=JobRecord)
async def cancel_job(
    job_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """Cancel a queued or running job."""
    try:
        return JobService.cancel_job(job_id, db)
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    except InvalidJobStateTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.post("/{job_id}/answer", response_model=JobRecord)
async def answer_job_question(
    job_id: str,
    request: JobAnswerRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """Answer an awaiting_input question and requeue the job."""
    try:
        return JobService.answer_input(job_id, answer=request.answer, data=request.data, db=db)
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    except InvalidJobStateTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
