"""
orchestrator_core/memory/semantic.py

Semantic memory storage and lifecycle management (Section 5.4 & Phase 7).
Stores user preferences, facts, and persistent profile data in SQLite (memory_items)
and ChromaDB vector index for semantic similarity search.

Supports:
  1. remember(): stores item with pending_review=1 by default (safety first).
  2. review_pending(): returns unconfirmed memory items.
  3. confirm() / reject(): owner confirmation workflow.
  4. list_memory_items() / get_memory_item(): filtered inspection.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import sqlite3
from typing import Any, Optional
import uuid

from orchestrator_core.models import MemoryItemKind, MemoryItemRecord
from orchestrator_core.storage.chroma_client import get_agent_collection

logger = logging.getLogger(__name__)


def _sync_to_chroma(
    item_id: str,
    text: str,
    metadata: dict[str, Any],
    client: Optional[Any] = None,
) -> None:
    """Best-effort upsert of memory item into ChromaDB."""
    try:
        coll = get_agent_collection("memory", client=client)
        # Filter None values from metadata for ChromaDB compatibility
        safe_meta = {k: ("" if v is None else str(v) if isinstance(v, (bool, int, float)) else str(v)) for k, v in metadata.items()}
        coll.upsert(
            ids=[item_id],
            documents=[text],
            metadatas=[safe_meta],
        )
    except Exception as exc:
        logger.warning("[memory] ChromaDB sync failed for item %s: %s", item_id, exc)


def _row_to_record(row: sqlite3.Row) -> MemoryItemRecord:
    """Convert a database row to a MemoryItemRecord."""
    created_at = datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"]
    updated_at = datetime.fromisoformat(row["updated_at"]) if isinstance(row["updated_at"], str) else row["updated_at"]
    return MemoryItemRecord(
        id=row["id"],
        kind=row["kind"],
        key=row["key"],
        value=row["value"],
        source_session_id=row["source_session_id"],
        source_message_id=row["source_message_id"],
        pending_review=bool(row["pending_review"]),
        created_at=created_at,
        updated_at=updated_at,
        deleted=bool(row["deleted"]),
    )


def remember(
    value: str,
    kind: MemoryItemKind = "fact",
    key: Optional[str] = None,
    source_session_id: Optional[str] = None,
    source_message_id: Optional[str] = None,
    pending_review: bool = True,
    db: Optional[sqlite3.Connection] = None,
    chroma_client: Optional[Any] = None,
) -> MemoryItemRecord:
    """
    Store a semantic fact or preference into memory_items and index into vector store.
    Defaults to pending_review=True until confirmed by owner.
    """
    if db is None:
        raise ValueError("A database connection is required.")

    valid_kinds = {"fact", "preference", "episode_summary"}
    if kind not in valid_kinds:
        raise ValueError(f"Invalid memory kind '{kind}'. Must be one of {valid_kinds}")

    item_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_val = value.strip()
    clean_key = key.strip() if key else None

    with db:
        db.execute(
            """
            INSERT INTO memory_items (
                id, kind, key, value, source_session_id, source_message_id,
                pending_review, created_at, updated_at, deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                item_id,
                kind,
                clean_key,
                clean_val,
                source_session_id,
                source_message_id,
                1 if pending_review else 0,
                now_iso,
                now_iso,
            ),
        )

    # Sync to vector collection
    doc_text = f"Key: {clean_key}\n{clean_val}" if clean_key else clean_val
    meta = {
        "id": item_id,
        "kind": kind,
        "key": clean_key or "",
        "pending_review": "1" if pending_review else "0",
        "source_session_id": source_session_id or "",
    }
    _sync_to_chroma(item_id, doc_text, meta, client=chroma_client)

    logger.info("[memory] Remembered %s (id=%s, pending=%s)", kind, item_id, pending_review)
    return get_memory_item(item_id, db)  # type: ignore[return-value]


def get_memory_item(item_id: str, db: sqlite3.Connection) -> Optional[MemoryItemRecord]:
    """Retrieve a single memory item by ID."""
    row = db.execute("SELECT * FROM memory_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return None
    return _row_to_record(row)


def list_memory_items(
    kind: Optional[str] = None,
    pending_review: Optional[bool] = None,
    include_deleted: bool = False,
    db: Optional[sqlite3.Connection] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MemoryItemRecord]:
    """List memory items matching filter criteria."""
    if db is None:
        raise ValueError("A database connection is required.")

    query = "SELECT * FROM memory_items WHERE 1=1"
    params: list[Any] = []

    if not include_deleted:
        query += " AND deleted = 0"

    if kind:
        query += " AND kind = ?"
        params.append(kind)

    if pending_review is not None:
        query += " AND pending_review = ?"
        params.append(1 if pending_review else 0)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, tuple(params)).fetchall()
    return [_row_to_record(r) for r in rows]


def review_pending(db: sqlite3.Connection, limit: int = 50) -> list[MemoryItemRecord]:
    """Return memory items awaiting owner confirmation."""
    return list_memory_items(pending_review=True, include_deleted=False, db=db, limit=limit)


def confirm(
    item_id: str,
    db: sqlite3.Connection,
    chroma_client: Optional[Any] = None,
) -> MemoryItemRecord:
    """Confirm a pending memory item, marking it trusted (pending_review=0)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with db:
        cursor = db.execute(
            """
            UPDATE memory_items
            SET pending_review = 0, updated_at = ?
            WHERE id = ? AND deleted = 0
            """,
            (now_iso, item_id),
        )
    if cursor.rowcount == 0:
        raise ValueError(f"Memory item '{item_id}' not found or already deleted.")

    item = get_memory_item(item_id, db)
    if item:
        doc_text = f"Key: {item.key}\n{item.value}" if item.key else item.value
        meta = {
            "id": item.id,
            "kind": item.kind,
            "key": item.key or "",
            "pending_review": "0",
            "source_session_id": item.source_session_id or "",
        }
        _sync_to_chroma(item_id, doc_text, meta, client=chroma_client)

    logger.info("[memory] Confirmed memory item %s", item_id)
    return item  # type: ignore[return-value]


def update_memory_item(
    item_id: str,
    value: Optional[str] = None,
    key: Optional[str] = None,
    pending_review: Optional[bool] = None,
    db: Optional[sqlite3.Connection] = None,
    chroma_client: Optional[Any] = None,
) -> MemoryItemRecord:
    """Update fields on an existing memory item."""
    if db is None:
        raise ValueError("A database connection is required.")

    item = get_memory_item(item_id, db)
    if not item or item.deleted:
        raise ValueError(f"Memory item '{item_id}' not found or deleted.")

    new_val = value.strip() if value is not None else item.value
    new_key = key.strip() if key is not None else item.key
    new_pending = pending_review if pending_review is not None else item.pending_review
    now_iso = datetime.now(timezone.utc).isoformat()

    with db:
        db.execute(
            """
            UPDATE memory_items
            SET value = ?, key = ?, pending_review = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_val, new_key, 1 if new_pending else 0, now_iso, item_id),
        )

    updated = get_memory_item(item_id, db)
    if updated:
        doc_text = f"Key: {updated.key}\n{updated.value}" if updated.key else updated.value
        meta = {
            "id": updated.id,
            "kind": updated.kind,
            "key": updated.key or "",
            "pending_review": "1" if updated.pending_review else "0",
            "source_session_id": updated.source_session_id or "",
        }
        _sync_to_chroma(item_id, doc_text, meta, client=chroma_client)

    logger.info("[memory] Updated memory item %s", item_id)
    return updated  # type: ignore[return-value]
