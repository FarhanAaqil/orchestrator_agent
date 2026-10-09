"""
orchestrator_core/jobs/service.py

Persistent Job Service managing autonomous work units, step traces,
atomic CAS job claims, heartbeats, and state transitions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from orchestrator_core.exceptions import (
    AgentDisabledError,
    JobNotFoundError,
    JobClaimConflictError,
)
from orchestrator_core.jobs.events import event_hub
from orchestrator_core.jobs.state_machine import validate_transition
from orchestrator_core.models import (
    JobRecord,
    JobStepRecord,
    JobStatus,
    JobStepKind,
    canonical_agent_name,
)
from orchestrator_core.storage.db import log_audit

logger = logging.getLogger(__name__)


class JobService:
    """Service layer for persistent job queues and execution checkpoints."""

    @staticmethod
    def create_job(
        agent: str,
        goal: str,
        db: sqlite3.Connection,
        params: Optional[dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        parent_job_id: Optional[str] = None,
        session_id: Optional[str] = None,
        schedule_id: Optional[str] = None,
        priority: int = 5,
        max_steps: int = 25,
        token_budget: int = 60000,
        not_before: Optional[datetime] = None,
    ) -> JobRecord:
        """Create and queue a new autonomous job."""
        canonical_agent = canonical_agent_name(agent)
        flag_rows = db.execute(
            "SELECT value FROM system_flags WHERE key IN (?, ?)",
            (f"agent_enabled_{canonical_agent}", f"agent_enabled_{agent}"),
        ).fetchall()
        for r in flag_rows:
            if r["value"].strip() == "0":
                logger.warning("Agent '%s' is administratively disabled. Cannot create job.", agent)
                raise AgentDisabledError(canonical_agent)

        job_id = str(uuid.uuid4())
        effective_thread_id = thread_id or str(uuid.uuid4())
        params_json = json.dumps(params or {}, separators=(",", ":"), sort_keys=True)
        created_at = datetime.now(timezone.utc).isoformat()
        not_before_str = not_before.isoformat() if not_before else None

        with db:
            db.execute(
                """
                INSERT INTO jobs (
                    id, thread_id, parent_job_id, session_id, schedule_id,
                    agent, goal, params_json, status, priority, attempts, max_attempts,
                    not_before, step_count, max_steps, token_budget, tokens_used,
                    cost_usd, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, 0, 3, ?, 0, ?, ?, 0, 0.0, ?)
                """,
                (
                    job_id,
                    effective_thread_id,
                    parent_job_id,
                    session_id,
                    schedule_id,
                    agent,
                    goal,
                    params_json,
                    priority,
                    not_before_str,
                    max_steps,
                    token_budget,
                    created_at,
                ),
            )

        log_audit(
            db,
            actor="jobs_service",
            event="job_created",
            entity="job",
            entity_id=job_id,
            detail={"agent": agent, "thread_id": effective_thread_id, "priority": priority},
        )

        event_hub.publish("job.created", {"job_id": job_id, "agent": agent, "goal": goal})
        logger.info("Job created — id=%s agent=%s thread_id=%s", job_id, agent, effective_thread_id)

        job = JobService.get_job(job_id, db)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    @staticmethod
    def get_job(job_id: str, db: sqlite3.Connection) -> Optional[JobRecord]:
        """Fetch a job record by ID."""
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return JobRecord(**dict(row))

    @staticmethod
    def list_jobs(
        db: sqlite3.Connection,
        status: Optional[str] = None,
        agent: Optional[str] = None,
        thread_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JobRecord], int]:
        """List jobs with filters and pagination."""
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if agent:
            clauses.append("agent = ?")
            params.append(agent)
        if thread_id:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        count_sql = f"SELECT COUNT(*) FROM jobs {where}"
        total = db.execute(count_sql, tuple(params)).fetchone()[0]

        data_sql = f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = db.execute(data_sql, (*params, limit, offset)).fetchall()

        return [JobRecord(**dict(r)) for r in rows], total

    @staticmethod
    def claim_job(worker_id: str, db: sqlite3.Connection) -> Optional[JobRecord]:
        """
        Atomic Compare-And-Set claim of the next available queued job (Section 5.4).
        Selects highest priority / oldest queued job ready to run.
        """
        now = datetime.now(timezone.utc).isoformat()
        with db:
            cur = db.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    claimed_by = ?,
                    claimed_at = ?,
                    heartbeat_at = ?,
                    attempts = attempts + 1,
                    started_at = COALESCE(started_at, ?)
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE status = 'queued' AND (not_before IS NULL OR not_before <= ?)
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                ) AND status = 'queued'
                RETURNING *;
                """,
                (worker_id, now, now, now, now),
            )
            row = cur.fetchone()

        if row is None:
            return None

        job = JobRecord(**dict(row))
        log_audit(
            db,
            actor="worker",
            event="job_claimed",
            entity="job",
            entity_id=job.id,
            detail={"worker_id": worker_id, "attempts": job.attempts},
        )
        event_hub.publish("job.claimed", {"job_id": job.id, "worker_id": worker_id})
        logger.info("Job claimed — id=%s worker=%s attempt=%d", job.id, worker_id, job.attempts)
        return job

    @staticmethod
    def heartbeat(job_id: str, worker_id: str, db: sqlite3.Connection) -> bool:
        """
        Update heartbeat timestamp for an active running job.
        Returns False if the job was cancelled or claimed by another worker.
        """
        now = datetime.now(timezone.utc).isoformat()
        with db:
            cur = db.execute(
                """
                UPDATE jobs
                SET heartbeat_at = ?
                WHERE id = ? AND claimed_by = ? AND status = 'running'
                """,
                (now, job_id, worker_id),
            )
        return cur.rowcount > 0

    @staticmethod
    def transition(
        job_id: str,
        target_status: JobStatus,
        db: sqlite3.Connection,
        result_json: Optional[str] = None,
        error: Optional[str] = None,
        not_before: Optional[datetime] = None,
        worker_id: Optional[str] = None,
    ) -> JobRecord:
        """
        Enforce state machine and transition a job to target_status.
        """
        job = JobService.get_job(job_id, db)
        if job is None:
            raise JobNotFoundError(job_id)

        validate_transition(job_id, job.status, target_status)

        now = datetime.now(timezone.utc).isoformat()
        finished_at = now if target_status in ("succeeded", "failed", "cancelled", "expired") else None
        not_before_str = not_before.isoformat() if not_before else None

        # Reset claimed_by and heartbeat when releasing back to queue
        new_claimed_by = None if target_status == "queued" else job.claimed_by
        new_heartbeat = None if target_status == "queued" else job.heartbeat_at

        with db:
            db.execute(
                """
                UPDATE jobs
                SET status = ?,
                    result_json = COALESCE(?, result_json),
                    error = COALESCE(?, error),
                    not_before = ?,
                    claimed_by = ?,
                    heartbeat_at = ?,
                    finished_at = COALESCE(?, finished_at)
                WHERE id = ?
                """,
                (
                    target_status,
                    result_json,
                    error,
                    not_before_str,
                    new_claimed_by,
                    new_heartbeat,
                    finished_at,
                    job_id,
                ),
            )

        log_audit(
            db,
            actor=worker_id or "job_service",
            event="job_transition",
            entity="job",
            entity_id=job_id,
            detail={"from_status": job.status, "to_status": target_status, "error": error},
        )

        event_hub.publish(
            "job.status_changed",
            {"job_id": job_id, "from": job.status, "to": target_status, "error": error},
        )
        logger.info("Job %s transitioned from %s to %s", job_id, job.status, target_status)

        updated = JobService.get_job(job_id, db)
        if updated is None:
            raise JobNotFoundError(job_id)
        return updated

    @staticmethod
    def record_step(
        job_id: str,
        idx: int,
        kind: JobStepKind,
        db: sqlite3.Connection,
        name: Optional[str] = None,
        input_json: Optional[str] = None,
        output_json: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
        duration_ms: Optional[int] = None,
        ok: bool = True,
    ) -> JobStepRecord:
        """
        Record a step execution checkpoint in job_steps and update job metrics.
        """
        step_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        delta_tokens = (tokens_in or 0) + (tokens_out or 0)
        delta_cost = cost_usd or 0.0

        with db:
            db.execute(
                """
                INSERT INTO job_steps (
                    id, job_id, idx, kind, name, input_json, output_json,
                    tokens_in, tokens_out, cost_usd, duration_ms, ok, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    job_id,
                    idx,
                    kind,
                    name,
                    input_json,
                    output_json,
                    tokens_in,
                    tokens_out,
                    cost_usd,
                    duration_ms,
                    1 if ok else 0,
                    created_at,
                ),
            )
            # Atomically update step_count and resource counters on the job
            db.execute(
                """
                UPDATE jobs
                SET step_count = step_count + 1,
                    tokens_used = tokens_used + ?,
                    cost_usd = cost_usd + ?
                WHERE id = ?
                """,
                (delta_tokens, delta_cost, job_id),
            )

        step = JobStepRecord(
            id=step_id,
            job_id=job_id,
            idx=idx,
            kind=kind,
            name=name,
            input_json=input_json,
            output_json=output_json,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            ok=ok,
            created_at=datetime.fromisoformat(created_at),
        )

        event_hub.publish(
            "job.step",
            {"job_id": job_id, "step_idx": idx, "kind": kind, "name": name, "ok": ok},
        )
        return step

    @staticmethod
    def get_steps(job_id: str, db: sqlite3.Connection) -> list[JobStepRecord]:
        """Retrieve all recorded steps for a job in chronological order."""
        rows = db.execute(
            "SELECT * FROM job_steps WHERE job_id = ? ORDER BY idx ASC",
            (job_id,),
        ).fetchall()
        return [JobStepRecord(**dict(r)) for r in rows]

    @staticmethod
    def answer_input(
        job_id: str,
        answer: str,
        db: sqlite3.Connection,
        data: Optional[dict[str, Any]] = None,
    ) -> JobRecord:
        """Answer an awaiting_input job question and requeue the job."""
        job = JobService.get_job(job_id, db)
        if job is None:
            raise JobNotFoundError(job_id)

        # Record answer as a note step
        steps = JobService.get_steps(job_id, db)
        next_idx = len(steps)
        payload = json.dumps({"answer": answer, "data": data or {}})

        JobService.record_step(
            job_id=job_id,
            idx=next_idx,
            kind="note",
            name="user_answer",
            output_json=payload,
            db=db,
        )

        # Transition back to queued so worker can pick it up
        return JobService.transition(job_id, "queued", db)

    @staticmethod
    def cancel_job(job_id: str, db: sqlite3.Connection) -> JobRecord:
        """Cancel a queued or running job."""
        return JobService.transition(job_id, "cancelled", db, error="Cancelled by user")
