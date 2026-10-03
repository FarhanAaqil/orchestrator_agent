"""
orchestrator_core/jobs/reaper.py

Zombie job recovery: detects abandoned 'running' jobs with dead heartbeats
and safely requeues them or fails them if max_attempts is exhausted (Section 5.4).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from orchestrator_core.jobs.service import JobService
from orchestrator_core.storage.db import log_audit

logger = logging.getLogger(__name__)


def reap_zombies(db: sqlite3.Connection, timeout_seconds: float = 60.0) -> list[str]:
    """
    Find and recover abandoned running jobs whose heartbeat has expired.
    Requeues if attempts < max_attempts; marks failed if attempts are exhausted.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)).isoformat()
    rows = db.execute(
        """
        SELECT id, attempts, max_attempts
        FROM jobs
        WHERE status = 'running'
          AND COALESCE(heartbeat_at, claimed_at) <= ?
        """,
        (cutoff,),
    ).fetchall()

    reaped_ids = []
    now = datetime.now(timezone.utc)

    for row in rows:
        job_id = row["id"]
        attempts = row["attempts"]
        max_attempts = row["max_attempts"]

        if attempts < max_attempts:
            # Requeue with 5s backoff
            backoff_time = now + timedelta(seconds=5)
            err_msg = f"Zombie job recovered: heartbeat expired (> {timeout_seconds:.0f}s)"
            JobService.transition(
                job_id=job_id,
                target_status="queued",
                db=db,
                error=err_msg,
                not_before=backoff_time,
            )
            log_audit(
                db,
                actor="reaper",
                event="zombie_requeued",
                entity="job",
                entity_id=job_id,
                detail={"attempts": attempts, "max_attempts": max_attempts},
            )
            logger.warning("Reaper requeued zombie job %s (attempt %d/%d)", job_id, attempts, max_attempts)
        else:
            # Exhausted max attempts
            err_msg = f"Zombie job aborted: worker heartbeat dead and attempts exhausted ({attempts}/{max_attempts})"
            JobService.transition(
                job_id=job_id,
                target_status="failed",
                db=db,
                error=err_msg,
            )
            log_audit(
                db,
                actor="reaper",
                event="zombie_failed",
                entity="job",
                entity_id=job_id,
                detail={"attempts": attempts, "max_attempts": max_attempts},
            )
            logger.error("Reaper failed zombie job %s (attempts exhausted)", job_id)

        reaped_ids.append(job_id)

    return reaped_ids
