"""
orchestrator_core/runner/caps.py

Hard safety guards and resource caps enforced before every step in the agent loop.
Enforces:
  1. Emergency kill switch (system_flags.kill_switch == 'on')
  2. Daily budget limit (system_flags.daily_budget_usd)
  3. Step count limit (job.max_steps)
  4. Token budget cap (job.token_budget)
  5. Wall-clock timeout (default 600s)
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone

from orchestrator_core.exceptions import (
    AgentDisabledError,
    BudgetExceededError,
    JobTimeoutError,
    KillSwitchActiveError,
    MaxStepsExceededError,
    TokenBudgetExceededError,
)
from orchestrator_core.models import JobRecord, canonical_agent_name

logger = logging.getLogger(__name__)


def check_guards(
    job: JobRecord,
    db: sqlite3.Connection,
    start_time: float | None = None,
    timeout_seconds: float = 600.0,
) -> None:
    """
    Evaluate all guardrails before step execution.
    Raises specialized JobError if any constraint is violated.
    """
    # 0. Agent administrative status check
    canonical_agent = canonical_agent_name(job.agent)
    row_agent = db.execute(
        "SELECT value FROM system_flags WHERE key IN (?, ?)",
        (f"agent_enabled_{canonical_agent}", f"agent_enabled_{job.agent}"),
    ).fetchall()
    for r in row_agent:
        if r["value"].strip() == "0":
            logger.warning("Agent '%s' is administratively disabled. Halting job %s", job.agent, job.id)
            raise AgentDisabledError(canonical_agent)

    # 1. Kill switch check
    row_ks = db.execute("SELECT value FROM system_flags WHERE key = 'kill_switch'").fetchone()
    if row_ks and row_ks["value"].strip().lower() == "on":
        logger.critical("Kill switch is ACTIVE! Aborting step execution for job %s", job.id)
        raise KillSwitchActiveError(f"Emergency kill switch is ACTIVE. Job {job.id} halted.")

    # 2. Daily budget check
    row_budget = db.execute("SELECT value FROM system_flags WHERE key = 'daily_budget_usd'").fetchone()
    budget_limit = float(row_budget["value"]) if row_budget else 5.0

    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cost_row = db.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) FROM jobs WHERE date(created_at) = ?",
        (today_utc,),
    ).fetchone()
    total_cost_today = float(cost_row[0]) if cost_row else 0.0

    if total_cost_today >= budget_limit:
        logger.critical(
            "Daily budget exceeded: $%.2f >= $%.2f. Halting job %s",
            total_cost_today, budget_limit, job.id,
        )
        raise BudgetExceededError(total_cost_today, budget_limit)

    # 3. Step cap check
    if job.step_count >= job.max_steps:
        logger.warning("Step cap reached for job %s: %d/%d", job.id, job.step_count, job.max_steps)
        raise MaxStepsExceededError(job.id, job.step_count, job.max_steps)

    # 4. Token budget check
    if job.tokens_used >= job.token_budget:
        logger.warning(
            "Token budget exhausted for job %s: %d/%d",
            job.id, job.tokens_used, job.token_budget,
        )
        raise TokenBudgetExceededError(job.id, job.tokens_used, job.token_budget)

    # 5. Wall-clock timeout check
    if start_time is not None:
        elapsed = time.monotonic() - start_time
        if elapsed > timeout_seconds:
            logger.warning("Wall-clock timeout reached for job %s: %.1fs > %.1fs", job.id, elapsed, timeout_seconds)
            raise JobTimeoutError(job.id, timeout_seconds)
