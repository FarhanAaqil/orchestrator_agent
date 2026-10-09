"""
orchestrator_core/memory/retrieval.py

Budgeted memory context retrieval (Phase 7).
Ranks and packs relevant semantic facts, user preferences, and prior episode summaries
into a compact XML context block (<relevant_memories>) within a strict token budget.
Guarantees:
  1. Never exceeds token_budget.
  2. Deleted (forgotten) items are strictly excluded.
  3. Pending unconfirmed items are excluded from general context unless requested.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional

from orchestrator_core.storage.chroma_client import get_agent_collection

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_BUDGET = 1500  # Default budget limit for injected memory slice


def _approx_tokens(text: str) -> int:
    """Fast approximation of token count (~4 characters per token)."""
    return max(1, len(text) // 4)


def get_context_slice(
    query: str,
    db: sqlite3.Connection,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    chroma_client: Optional[Any] = None,
    include_pending: bool = False,
) -> str:
    """
    Retrieve ranked semantic and episodic memories matching query within token_budget.
    Returns formatted <relevant_memories> block or empty string if no relevant memories exist.
    """
    if not query.strip() or token_budget <= 0:
        return ""

    matched_items: dict[str, dict[str, Any]] = {}

    # 1. Vector similarity search in ChromaDB (memory collection)
    try:
        coll = get_agent_collection("memory", client=chroma_client)
        res = coll.query(query_texts=[query], n_results=5)
        if res and res.get("ids") and res["ids"][0]:
            for item_id, doc in zip(res["ids"][0], res["documents"][0]):
                matched_items[item_id] = {"doc": doc, "score": 1}
    except Exception as exc:
        logger.debug("[retrieval] Chroma memory query error: %s", exc)

    # 2. Vector similarity search in ChromaDB (episodes collection)
    try:
        ep_coll = get_agent_collection("episodes", client=chroma_client)
        ep_res = ep_coll.query(query_texts=[query], n_results=3)
        if ep_res and ep_res.get("ids") and ep_res["ids"][0]:
            for item_id, doc in zip(ep_res["ids"][0], ep_res["documents"][0]):
                if item_id not in matched_items:
                    matched_items[item_id] = {"doc": doc, "score": 2}
    except Exception as exc:
        logger.debug("[retrieval] Chroma episodes query error: %s", exc)

    # 3. Always check SQLite directly for active confirmed preferences and facts
    # (acts as high-signal base layer even if vector database is empty or cold)
    pending_clause = "" if include_pending else "AND pending_review = 0"
    rows = db.execute(
        f"""
        SELECT id, kind, key, value, created_at
        FROM memory_items
        WHERE deleted = 0 {pending_clause}
        ORDER BY updated_at DESC
        LIMIT 10
        """
    ).fetchall()

    for r in rows:
        item_id = r["id"]
        if item_id not in matched_items:
            # Simple keyword overlap or recent preference boost
            doc = f"Key: {r['key']}\n{r['value']}" if r["key"] else r["value"]
            matched_items[item_id] = {"doc": doc, "score": 3}

    if not matched_items:
        return ""

    # 4. Filter against SQLite ground truth to ensure zero deleted items and verify review status
    valid_entries: list[str] = []
    placeholders = ",".join("?" for _ in matched_items)
    check_rows = db.execute(
        f"""
        SELECT id, kind, key, value, pending_review, deleted, created_at
        FROM memory_items
        WHERE id IN ({placeholders}) AND deleted = 0 {pending_clause}
        """,
        list(matched_items.keys()),
    ).fetchall()

    for r in check_rows:
        kind = r["kind"]
        val = r["value"]
        key_str = f" ({r['key']})" if r["key"] else ""
        date_str = str(r["created_at"])[:10]
        entry = f"- [{kind.upper()}{key_str}] {val} (recorded: {date_str})"
        valid_entries.append(entry)

    if not valid_entries:
        return ""

    # 5. Pack entries within token_budget
    budget_remaining = token_budget - _approx_tokens("<relevant_memories>\n</relevant_memories>\n")
    packed_lines: list[str] = []

    for entry in valid_entries:
        cost = _approx_tokens(entry + "\n")
        if cost <= budget_remaining:
            packed_lines.append(entry)
            budget_remaining -= cost
        else:
            # If no items packed yet and budget allows at least partial content
            if not packed_lines and budget_remaining > 20:
                truncated = entry[: budget_remaining * 4 - 20] + "... [truncated]"
                packed_lines.append(truncated)
            break

    if not packed_lines:
        return ""

    body = "\n".join(packed_lines)
    return f"<relevant_memories>\n{body}\n</relevant_memories>"
