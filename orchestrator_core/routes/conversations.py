"""
orchestrator_core/routes/conversations.py

Multi-chat conversation management and message persistence endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import sqlite3
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from orchestrator_core.storage.db import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversations", tags=["Conversations"])


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, description="Optional title for the conversation thread")


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    agent: Optional[str] = None
    created_at: str


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """List all conversations ordered by last updated."""
    query = """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as message_count
        FROM conversations c
        ORDER BY c.updated_at DESC
        LIMIT ? OFFSET ?
    """
    rows = db.execute(query, (limit, offset)).fetchall()
    return [
        ConversationResponse(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            message_count=row["message_count"],
        )
        for row in rows
    ]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: Optional[ConversationCreate] = None,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Create a new conversation session."""
    cid = str(uuid.uuid4())
    title = (body.title.strip() if body and body.title else "New Chat") or "New Chat"
    now = datetime.now(timezone.utc).isoformat()

    with db:
        db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, now, now),
        )

    return ConversationResponse(
        id=cid,
        title=title,
        created_at=now,
        updated_at=now,
        message_count=0,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Get conversation metadata by ID."""
    row = db.execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as message_count
        FROM conversations c
        WHERE c.id = ?
        """,
        (conversation_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conversation '{conversation_id}' not found")

    return ConversationResponse(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=row["message_count"],
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Retrieve message history for a conversation thread in chronological order."""
    # Verify conversation exists
    c = db.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conversation '{conversation_id}' not found")

    rows = db.execute(
        """
        SELECT id, conversation_id, role, content, agent, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (conversation_id, limit),
    ).fetchall()

    return [
        MessageResponse(
            id=r["id"],
            conversation_id=r["conversation_id"],
            role=r["role"],
            content=r["content"],
            agent=r["agent"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """Delete a conversation thread and all its messages."""
    row = db.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conversation '{conversation_id}' not found")

    with db:
        db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    return {"deleted": True, "id": conversation_id}
