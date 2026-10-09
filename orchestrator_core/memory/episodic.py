"""
orchestrator_core/memory/episodic.py

Episodic memory summarizer (Phase 7).
Transforms long multi-turn conversation sessions into compact, high-signal episode summaries.
Indexes summaries in ChromaDB ('episodes' collection) and SQLite ('memory_items').
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import sqlite3
from typing import Any, Callable, Optional
import uuid

from groq import Groq

from orchestrator_core.config import get_settings
from orchestrator_core.models import MemoryItemRecord
from orchestrator_core.storage.chroma_client import get_agent_collection

logger = logging.getLogger(__name__)

_EPISODE_PROMPT = """You are the Memory Architect for Farhan Aaqil's Orchestrator system.
Analyze the following multi-turn conversation transcript and extract a compact, high-signal episodic summary.

Output format:
- **Topic**: Main subject discussed.
- **Key Decisions**: Decisions made, conclusions reached, or preferences expressed.
- **Artifacts / Outputs**: Code, proposals, plans, or research outputs produced.
- **Pending Follow-ups**: Unfinished items or future tasks mentioned.

Be concise, dense with technical details, and avoid pleasantries or fluff."""


def _default_llm_summarize(transcript: str) -> str:
    """Summarize transcript via Groq LLM."""
    settings = get_settings()
    try:
        client = Groq(api_key=settings.groq_api_key)
        resp = client.chat.completions.create(
            model=settings.router_model,
            messages=[
                {"role": "system", "content": _EPISODE_PROMPT},
                {"role": "user", "content": f"Transcript:\n{transcript}"},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return resp.choices[0].message.content or "Episode summarized."
    except Exception as exc:
        logger.warning("[episodic] Groq summarization call failed: %s — using rule-based summary.", exc)
        lines = [line.strip() for line in transcript.split("\n") if line.strip()]
        first_few = " | ".join(lines[:3]) if lines else "Empty session"
        return f"Session Synopsis: {first_few[:200]}"


def summarize_session(
    session_id: str,
    db: sqlite3.Connection,
    llm_callable: Optional[Callable[[str], str]] = None,
    chroma_client: Optional[Any] = None,
) -> Optional[MemoryItemRecord]:
    """
    Summarize a completed or idle conversation session into an episodic memory item.
    Persists to SQLite memory_items and indexes into ChromaDB 'episodes' collection.
    """
    # 1. Fetch conversation messages
    rows = db.execute(
        """
        SELECT role, content, agent, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
        """,
        (session_id,),
    ).fetchall()

    if not rows:
        logger.info("[episodic] No messages found for session %s — skipping summary.", session_id)
        return None

    # Format transcript
    transcript_lines = []
    for r in rows:
        speaker = r["agent"] or r["role"]
        transcript_lines.append(f"[{speaker}]: {r['content']}")
    full_transcript = "\n".join(transcript_lines)

    # 2. Generate summary
    if llm_callable:
        summary_text = llm_callable(full_transcript)
    else:
        summary_text = _default_llm_summarize(full_transcript)

    # 3. Store in SQLite memory_items
    item_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute(
            """
            INSERT INTO memory_items (
                id, kind, key, value, source_session_id, source_message_id,
                pending_review, created_at, updated_at, deleted
            ) VALUES (?, 'episode_summary', ?, ?, ?, NULL, 0, ?, ?, 0)
            """,
            (
                item_id,
                f"session_summary_{session_id[:8]}",
                summary_text.strip(),
                session_id,
                now_iso,
                now_iso,
            ),
        )

    # 4. Sync to ChromaDB
    try:
        coll = get_agent_collection("episodes", client=chroma_client)
        coll.upsert(
            ids=[item_id],
            documents=[summary_text.strip()],
            metadatas=[{
                "id": item_id,
                "kind": "episode_summary",
                "source_session_id": session_id,
            }],
        )
        logger.info("[episodic] Episode summary vector stored in ChromaDB (id=%s).", item_id)
    except Exception as exc:
        logger.warning("[episodic] ChromaDB sync failed for episode %s: %s", item_id, exc)

    logger.info("[episodic] Session %s summarized into episode %s.", session_id, item_id)
    # Fetch and return created record
    row = db.execute("SELECT * FROM memory_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return None

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
