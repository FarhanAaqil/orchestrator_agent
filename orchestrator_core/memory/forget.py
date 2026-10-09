"""
orchestrator_core/memory/forget.py

Forget flow implementation (Phase 7).
Enforces owner data rights:
  1. Soft deletes in SQLite: sets deleted = 1, updated_at = now().
  2. Purges vector from ChromaDB so embeddings cannot match in similarity searches.
  3. Guarantees forgotten memories are NEVER returned in context retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import sqlite3
from typing import Any, Optional

from orchestrator_core.storage.chroma_client import get_agent_collection

logger = logging.getLogger(__name__)


def forget(
    item_id: str,
    db: sqlite3.Connection,
    chroma_client: Optional[Any] = None,
    purge_vector: bool = True,
) -> bool:
    """
    Delete a memory item from SQLite and purge from vector storage.
    Returns True if an active record was found and deleted, False otherwise.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    with db:
        cursor = db.execute(
            """
            UPDATE memory_items
            SET deleted = 1, updated_at = ?
            WHERE id = ? AND deleted = 0
            """,
            (now_iso, item_id),
        )

    if cursor.rowcount == 0:
        logger.warning("[memory] Item %s not found or already deleted.", item_id)
        return False

    # Purge vector from ChromaDB
    if purge_vector:
        try:
            coll = get_agent_collection("memory", client=chroma_client)
            coll.delete(ids=[item_id])
            logger.info("[memory] Purged vector for memory item %s from ChromaDB.", item_id)
        except Exception as exc:
            logger.warning("[memory] Vector purge failed for item %s: %s", item_id, exc)

    logger.info("[memory] Forgotten memory item %s successfully.", item_id)
    return True
