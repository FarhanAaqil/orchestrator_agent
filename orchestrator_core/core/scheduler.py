"""
orchestrator_core/core/scheduler.py

Background job scheduler for Orchestrator v2.

Only 2 recurring jobs:
  1. daily_briefing — runs once at system startup then at a configurable hour/interval
  2. stale_approval_cleanup — marks expired 'pending' approvals as 'expired'

Uses APScheduler (BackgroundScheduler) — started and shut down inside the
FastAPI lifespan context manager (orchestrator_core/main.py).

Design constraints:
  - No distributed locking. Single-process use only.
  - No heavy imports at module level — all agent/gate imports are deferred to
    job functions to prevent circular imports.
  - Jobs log at INFO on every run so every execution is auditable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler = None  # Module-level reference so lifespan can call shutdown()


def _daily_briefing_job() -> None:
    """
    Compose a brief daily status summary using the career_agent.
    Logs the output — does NOT send email (that requires approval via the gate).
    """
    from orchestrator_core.agents import career_agent
    from orchestrator_core.models import PipelineRequest

    logger.info("[scheduler] Running daily_briefing job — %s", datetime.now(timezone.utc).isoformat())
    try:
        result = career_agent.handle(
            "Give me a brief daily status summary of active career priorities and upcoming actions."
        )
        logger.info("[scheduler] daily_briefing result (first 200 chars): %.200s", result.output)
    except Exception:
        logger.exception("[scheduler] daily_briefing job failed")


def _stale_approval_cleanup_job() -> None:
    """
    Mark pending approvals that are past their expires_at as 'expired'.
    Runs periodically to prevent approvals from staying in 'pending' forever.
    """
    from orchestrator_core.storage.db import get_db

    logger.info("[scheduler] Running stale_approval_cleanup — %s", datetime.now(timezone.utc).isoformat())
    try:
        db = get_db()
        now_iso = datetime.now(timezone.utc).isoformat()
        with db:
            cur = db.execute(
                "UPDATE approvals SET status = 'expired' "
                "WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at < ?",
                (now_iso,),
            )
        if cur.rowcount:
            logger.info("[scheduler] Marked %d stale approvals as expired", cur.rowcount)
        db.close()
    except Exception:
        logger.exception("[scheduler] stale_approval_cleanup job failed")


def start_scheduler(daily_briefing_hour: int = 8) -> None:
    """
    Start the APScheduler BackgroundScheduler with both recurring jobs.

    Args:
        daily_briefing_hour: UTC hour at which the daily briefing fires (default 08:00 UTC).
    """
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning(
            "APScheduler not installed — background scheduler will not start. "
            "Install it with: pip install apscheduler"
        )
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Job 1: daily briefing — every day at configured UTC hour
    _scheduler.add_job(
        _daily_briefing_job,
        trigger=CronTrigger(hour=daily_briefing_hour, minute=0, timezone="UTC"),
        id="daily_briefing",
        name="Daily Briefing",
        replace_existing=True,
    )

    # Job 2: stale approval cleanup — every 30 minutes
    _scheduler.add_job(
        _stale_approval_cleanup_job,
        trigger=IntervalTrigger(minutes=30),
        id="stale_approval_cleanup",
        name="Stale Approval Cleanup",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — daily_briefing at %02d:00 UTC, stale_approval_cleanup every 30 min",
        daily_briefing_hour,
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler (called in FastAPI lifespan teardown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
