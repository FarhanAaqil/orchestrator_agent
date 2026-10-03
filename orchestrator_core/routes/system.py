"""
orchestrator_core/routes/system.py

System administrative and control plane endpoints:
  POST /system/kill-switch  — Emergency system kill switch (toggles runner halts)
  GET  /system/flags        — List all runtime system flags and controls
  POST /system/budget       — Configure daily budget ceiling
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from orchestrator_core.dependencies import verify_bearer_token
from orchestrator_core.models import KillSwitchRequest, SystemFlagRecord
from orchestrator_core.storage.db import get_db_connection, log_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["System"])


class DailyBudgetRequest(BaseModel):
    daily_budget_usd: float = Field(gt=0.0, description="Maximum daily spend limit in USD")


@router.post("/kill-switch")
async def toggle_kill_switch(
    request: KillSwitchRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """
    Emergency kill switch (Section 5.5).
    When active ('on'), all running agent steps halt immediately and no new jobs are claimed.
    """
    val = "on" if request.on else "off"
    now = datetime.now(timezone.utc).isoformat()

    with db:
        db.execute(
            """
            INSERT INTO system_flags (key, value, updated_at)
            VALUES ('kill_switch', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (val, now),
        )

    log_audit(
        db,
        actor="admin",
        event="kill_switch_toggled",
        entity="system_flag",
        entity_id="kill_switch",
        detail={"status": val},
    )
    logger.critical("System kill switch set to: %s", val)
    return {"kill_switch": val, "updated_at": now}


@router.get("/flags", response_model=list[SystemFlagRecord])
async def get_system_flags(
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """Retrieve all system flags and runtime control values."""
    rows = db.execute("SELECT key, value, updated_at FROM system_flags ORDER BY key ASC").fetchall()
    return [SystemFlagRecord(**dict(r)) for r in rows]


@router.post("/budget")
async def set_daily_budget(
    request: DailyBudgetRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
    _token: Optional[str] = Depends(verify_bearer_token),
):
    """Update system-wide daily budget limit in USD."""
    val = f"{request.daily_budget_usd:.2f}"
    now = datetime.now(timezone.utc).isoformat()

    with db:
        db.execute(
            """
            INSERT INTO system_flags (key, value, updated_at)
            VALUES ('daily_budget_usd', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (val, now),
        )

    log_audit(
        db,
        actor="admin",
        event="daily_budget_updated",
        entity="system_flag",
        entity_id="daily_budget_usd",
        detail={"daily_budget_usd": request.daily_budget_usd},
    )
    logger.info("Daily budget ceiling updated to: $%s", val)
    return {"daily_budget_usd": float(val), "updated_at": now}
