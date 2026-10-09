"""
orchestrator_core/routes/memory.py

Memory management REST API endpoints (Phase 7).
Provides endpoints for memory CRUD, pending-review queues, confirmation, and session summarization.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from orchestrator_core.memory.episodic import summarize_session
from orchestrator_core.memory.forget import forget
from orchestrator_core.memory.semantic import (
    confirm,
    get_memory_item,
    list_memory_items,
    remember,
    update_memory_item,
)
from orchestrator_core.models import (
    MemoryItemCreate,
    MemoryItemRecord,
    MemoryItemResponse,
    MemoryItemUpdate,
)
from orchestrator_core.storage.db import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["Memory"])


def _to_response(rec: MemoryItemRecord) -> MemoryItemResponse:
    """Map MemoryItemRecord to API response shape."""
    return MemoryItemResponse(
        id=rec.id,
        kind=rec.kind,
        key=rec.key,
        value=rec.value,
        source_session_id=rec.source_session_id,
        source_message_id=rec.source_message_id,
        pending_review=rec.pending_review,
        created_at=rec.created_at.isoformat(),
        updated_at=rec.updated_at.isoformat(),
        deleted=rec.deleted,
    )


@router.get("", response_model=list[MemoryItemResponse])
async def list_memories(
    kind: Optional[str] = Query(default=None, description="Filter by kind ('fact', 'preference', 'episode_summary')"),
    pending_review: Optional[bool] = Query(default=None, description="Filter by pending review status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """List memory items with optional kind and review status filters."""
    items = list_memory_items(
        kind=kind,
        pending_review=pending_review,
        include_deleted=False,
        db=db,
        limit=limit,
        offset=offset,
    )
    return [_to_response(i) for i in items]


@router.post("", response_model=MemoryItemResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryItemCreate,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Store a new fact, preference, or memory item."""
    try:
        rec = remember(
            value=body.value,
            kind=body.kind,
            key=body.key,
            source_session_id=body.source_session_id,
            source_message_id=body.source_message_id,
            pending_review=body.pending_review,
            db=db,
        )
        return _to_response(rec)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{memory_id}", response_model=MemoryItemResponse)
async def get_memory(
    memory_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Retrieve a specific memory item by ID."""
    rec = get_memory_item(memory_id, db)
    if not rec or rec.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory item '{memory_id}' not found")
    return _to_response(rec)


@router.patch("/{memory_id}", response_model=MemoryItemResponse)
async def update_memory(
    memory_id: str,
    body: MemoryItemUpdate,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Edit memory item key, value, or review confirmation status."""
    try:
        rec = update_memory_item(
            item_id=memory_id,
            value=body.value,
            key=body.key,
            pending_review=body.pending_review,
            db=db,
        )
        return _to_response(rec)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{memory_id}/confirm", response_model=MemoryItemResponse)
async def confirm_memory(
    memory_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Confirm a pending memory item, marking it trusted."""
    try:
        rec = confirm(memory_id, db)
        return _to_response(rec)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Delete a memory item and purge its vector representation."""
    ok = forget(memory_id, db, purge_vector=True)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory item '{memory_id}' not found")
    return {"deleted": True, "id": memory_id}


@router.post("/summarize/{session_id}", response_model=MemoryItemResponse)
async def summarize_conversation_session(
    session_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Summarize a conversation session and store its episodic memory summary."""
    rec = summarize_session(session_id, db)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No messages found for session '{session_id}' to summarize.",
        )
    return _to_response(rec)
