"""
orchestrator_core/routes/dispatch.py

POST /dispatch — classify a command, maintain persistent multi-chat conversation memory,
and execute against the resolved agent.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import sqlite3
import time
from typing import Optional
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
import json
from pydantic import BaseModel

from orchestrator_core.core.approval_gate import request_approval
from orchestrator_core.core.router import classify
from orchestrator_core.models import AgentResult, ClarificationNeeded, ErrorResponse, RouterResult
from orchestrator_core.storage.db import get_db, get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dispatch", tags=["Routing"])


def _get_agent_registry() -> dict:
    from orchestrator_core.agents import (
        career_agent,
        critic_agent,
        email_agent,
        general_chat_agent,
        github_agent,
        growth_content_agent,
        info_agent,
        linkedin_agent,
        research_agent,
    )
    return {
        "career_agent": career_agent.handle,
        "research_agent": research_agent.handle,
        "growth_content_agent": growth_content_agent.handle,
        "critic_agent": critic_agent.handle,
        "info_agent": info_agent.handle,
        "email_agent": email_agent.handle,
        "github_agent": github_agent.handle,
        "linkedin_agent": linkedin_agent.handle,
        "general_chat_agent": general_chat_agent.handle,
    }


class DispatchRequest(BaseModel):
    command: str
    context: dict = {}
    conversation_id: Optional[str] = None


@router.post("", response_model=None)
async def dispatch_command(
    body: DispatchRequest,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """
    Classify and immediately execute a command within a persistent conversation thread.
    Injects past conversational context and saves the interaction to SQLite.
    """
    t_start = time.monotonic()
    logger.info("Dispatching command: %.80s", body.command)
    now = datetime.now(timezone.utc).isoformat()

    # 1. Resolve or create conversation session
    cid = body.conversation_id
    if cid:
        row = db.execute("SELECT id FROM conversations WHERE id = ?", (cid,)).fetchone()
        if not row:
            title = body.command[:40] + ("..." if len(body.command) > 40 else "")
            with db:
                db.execute(
                    "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (cid, title, now, now),
                )
    else:
        cid = str(uuid.uuid4())
        title = body.command[:40] + ("..." if len(body.command) > 40 else "")
        with db:
            db.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (cid, title, now, now),
            )

    # 2. Retrieve last 10 messages for conversation context
    history_rows = db.execute(
        """
        SELECT role, content, agent
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
        LIMIT 10
        """,
        (cid,),
    ).fetchall()

    history_text = "\n".join(
        f"{r['role'].upper()} ({r['agent'] or 'user'}): {r['content']}"
        for r in history_rows
    )

    # 3. Store user message in messages table
    user_msg_id = str(uuid.uuid4())
    with db:
        db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, agent, created_at) VALUES (?, ?, 'user', ?, NULL, ?)",
            (user_msg_id, cid, body.command, now),
        )

    # 4. Route command
    classification = classify(body.command)

    if isinstance(classification, ClarificationNeeded):
        logger.info("Dispatch blocked — clarification needed: %s", classification.candidates)
        # Store clarifying assistant message in thread
        asst_msg_id = str(uuid.uuid4())
        clarification_msg = f"Clarification required: {classification.reasoning}. Options: {', '.join(classification.candidates)}"
        with db:
            db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, agent, created_at) VALUES (?, ?, 'assistant', ?, 'router', ?)",
                (asst_msg_id, cid, clarification_msg, now),
            )
            db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))
        return JSONResponse(
            status_code=422,
            content=classification.model_dump(),
        )

    assert isinstance(classification, RouterResult)
    agent_name = classification.agent
    registry = _get_agent_registry()

    if agent_name not in registry:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="AGENT_NOT_FOUND",
                detail=f"Agent '{agent_name}' is not registered in the dispatch registry.",
            ).model_dump(),
        )

    # 5. Execute agent with context injection
    handler = registry[agent_name]
    agent_meta = {
        "context": body.context,
        "conversation_id": cid,
        "conversation_history_text": history_text,
    }
    result: AgentResult = handler(body.command, metadata=agent_meta)

    # 6. Auto-queue approval if write action is triggered and not yet queued
    if result.action_type and not result.approval_id:
        approval_payload = result.metadata.get("approval_payload") or {
            "command": body.command,
            "action_type": result.action_type,
            "agent": agent_name,
        }
        try:
            app_id = request_approval(action_type=result.action_type, payload=approval_payload, db=db)
            result.approval_id = app_id
            result.metadata["approval_id"] = app_id
        except Exception as exc:
            logger.warning("Could not auto-queue approval record: %s", exc)

    latency_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        "Dispatch complete — agent=%s confidence=%.2f latency_ms=%d",
        agent_name,
        classification.confidence,
        latency_ms,
    )

    result.metadata["latency_ms"] = latency_ms
    result.metadata["confidence"] = classification.confidence
    result.metadata["reasoning"] = classification.reasoning
    result.metadata["conversation_id"] = cid

    # 7. Store assistant message in messages table & update conversation timestamp
    asst_msg_id = str(uuid.uuid4())
    with db:
        db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, agent, created_at) VALUES (?, ?, 'assistant', ?, ?, ?)",
            (asst_msg_id, cid, result.output, agent_name, now),
        )
        db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))

    return result


@router.post("/stream")
async def dispatch_command_stream(body: DispatchRequest):
    """
    Classify and stream responses in real-time via Server-Sent Events (§5c No-Lag).
    Perceived latency drops to 200-400ms for the first token.
    """
    def event_stream():
        t_start = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        db = get_db()
        try:
            # 1. Resolve or create conversation session
            cid = body.conversation_id
            if cid:
                row = db.execute("SELECT id FROM conversations WHERE id = ?", (cid,)).fetchone()
                if not row:
                    title = body.command[:40] + ("..." if len(body.command) > 40 else "")
                    with db:
                        db.execute(
                            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                            (cid, title, now, now),
                        )
            else:
                cid = str(uuid.uuid4())
                title = body.command[:40] + ("..." if len(body.command) > 40 else "")
                with db:
                    db.execute(
                        "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (cid, title, now, now),
                    )

            # 2. Retrieve history context
            history_rows = db.execute(
                """
                SELECT role, content, agent
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT 10
                """,
                (cid,),
            ).fetchall()

            history_text = "\n".join(
                f"{r['role'].upper()} ({r['agent'] or 'user'}): {r['content']}"
                for r in history_rows
            )

            # 3. Store user message
            user_msg_id = str(uuid.uuid4())
            with db:
                db.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, agent, created_at) VALUES (?, ?, 'user', ?, NULL, ?)",
                    (user_msg_id, cid, body.command, now),
                )

            # 4. Route command
            classification = classify(body.command)

            if isinstance(classification, ClarificationNeeded):
                clarification_msg = f"Clarification required: {classification.reasoning}. Options: {', '.join(classification.candidates)}"
                asst_msg_id = str(uuid.uuid4())
                with db:
                    db.execute(
                        "INSERT INTO messages (id, conversation_id, role, content, agent, created_at) VALUES (?, ?, 'assistant', ?, 'router', ?)",
                        (asst_msg_id, cid, clarification_msg, now),
                    )
                    db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))
                yield f"event: clarification\ndata: {json.dumps(classification.model_dump())}\n\n"
                return

            assert isinstance(classification, RouterResult)
            agent_name = classification.agent
            registry = _get_agent_registry()

            if agent_name not in registry:
                err_data = {"error": "AGENT_NOT_FOUND", "detail": f"Agent '{agent_name}' not found."}
                yield f"event: error\ndata: {json.dumps(err_data)}\n\n"
                return

            # Yield metadata event immediately so frontend knows which agent was routed
            yield f"event: meta\ndata: {json.dumps({'agent': agent_name, 'conversation_id': cid, 'confidence': classification.confidence, 'reasoning': classification.reasoning})}\n\n"

            accumulated_output = []

            # 5. Execution (streaming for general_chat_agent, handler for specialized agents)
            if agent_name == "general_chat_agent":
                from orchestrator_core.agents import general_chat_agent
                for token in general_chat_agent.stream_llm(body.command, context_history=history_text):
                    accumulated_output.append(token)
                    yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
                full_text = "".join(accumulated_output)
                action_type = None
                approval_id = None
            else:
                handler = registry[agent_name]
                agent_meta = {
                    "context": body.context,
                    "conversation_id": cid,
                    "conversation_history_text": history_text,
                }
                result: AgentResult = handler(body.command, metadata=agent_meta)
                full_text = result.output
                action_type = result.action_type
                approval_id = result.approval_id
                # Auto-queue approval if write action
                if action_type and not approval_id:
                    approval_payload = result.metadata.get("approval_payload") or {
                        "command": body.command,
                        "action_type": action_type,
                        "agent": agent_name,
                    }
                    try:
                        app_id = request_approval(action_type=action_type, payload=approval_payload, db=db)
                        approval_id = app_id
                    except Exception as exc:
                        logger.warning("Could not auto-queue approval record in stream: %s", exc)
                # Yield entire output as token chunk
                yield f"event: token\ndata: {json.dumps({'token': full_text})}\n\n"

            latency_ms = int((time.monotonic() - t_start) * 1000)

            # 6. Save assistant output to messages table
            asst_msg_id = str(uuid.uuid4())
            with db:
                db.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, agent, created_at) VALUES (?, ?, 'assistant', ?, ?, ?)",
                    (asst_msg_id, cid, full_text, agent_name, now),
                )
                db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))

            # Final done event
            yield f"event: done\ndata: {json.dumps({'output': full_text, 'agent': agent_name, 'action_type': action_type, 'approval_id': approval_id, 'latency_ms': latency_ms, 'conversation_id': cid})}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
