"""
orchestrator_core/tools/propose/propose_action.py

Action proposal tool (Capability.PROPOSE).
The ONLY state-modifying action tool exposed to agents.
Inserts a pending proposal into the approvals table (via request_approval)
and halts agent autonomy until a human explicitly authorizes and executes the action.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Optional
from pydantic import BaseModel, Field

from orchestrator_core.config import get_settings
from orchestrator_core.core.approval_gate import request_approval
from orchestrator_core.storage.db import get_db

logger = logging.getLogger(__name__)

SUPPORTED_PROPOSAL_TYPES = {
    "send_email",
    "publish_hashnode",
    "publish_devto",
    "linkedin_post",
    "github_create_issue",
    "github_comment",
}


class ProposeActionArgs(BaseModel):
    """Arguments for propose_action tool."""
    action_type: str = Field(
        description="The side-effect action type: 'send_email', 'publish_hashnode', 'publish_devto', 'linkedin_post', 'github_create_issue', 'github_comment'."
    )
    payload: dict[str, Any] = Field(
        description="Dictionary of parameters for the action (e.g. to_email, subject, body, content, title)."
    )
    target: Optional[str] = Field(
        default=None,
        description="Target recipient, platform, or repository destination.",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Unique idempotency key preventing duplicate action creation.",
    )


def propose_action(
    action_type: str,
    payload: dict[str, Any],
    target: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    db: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """
    Queue an external action for human review.
    Returns approval record metadata.
    """
    clean_type = action_type.strip().lower()

    own_db = False
    if db is None:
        db = get_db(get_settings().database_path)
        own_db = True

    try:
        approval_id = request_approval(
            action_type=clean_type,
            payload=payload,
            db=db,
            target=target,
            idempotency_key=idempotency_key,
        )
        logger.info("[propose_action] Action proposal queued — id=%s action=%s", approval_id, clean_type)
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action_type": clean_type,
            "target": target,
            "message": f"Action '{clean_type}' successfully queued for human approval. Awaiting decision.",
        }
    finally:
        if own_db:
            db.close()
