"""
tests/test_conversations.py

Tests for conversation memory, multi-chat endpoints, message history,
and agent capability roster.
"""

import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient

from orchestrator_core.config import get_settings
from orchestrator_core.main import app
from orchestrator_core.storage.db import get_db, run_migrations


@pytest.fixture
def client_with_clean_db(tmp_path, monkeypatch):
    """Provide a TestClient connected to an isolated test database with migrations applied."""
    db_file = tmp_path / "test_orchestrator.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    # Ensure auth token is unset for simple testing
    monkeypatch.delenv("ORCHESTRATOR_AUTH_TOKEN", raising=False)
    get_settings.cache_clear()

    conn = get_db(str(db_file))
    run_migrations(conn)
    conn.close()

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_list_agents_endpoint(client_with_clean_db):
    """GET /agents should return all 9 active agents and their capabilities."""
    response = client_with_clean_db.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 9
    agent_ids = {a["id"] for a in agents}
    expected_ids = {
        "career_agent",
        "research_agent",
        "growth_content_agent",
        "critic_agent",
        "info_agent",
        "email_agent",
        "github_agent",
        "linkedin_agent",
        "general_chat_agent",
    }
    assert agent_ids == expected_ids


def test_create_and_list_conversations(client_with_clean_db):
    """Test conversation thread creation, retrieval, and listing."""
    # Create thread
    res = client_with_clean_db.post("/conversations", json={"title": "Career Architecture Strategy"})
    assert res.status_code == 201
    conv = res.json()
    assert conv["title"] == "Career Architecture Strategy"
    assert conv["id"] is not None
    assert conv["message_count"] == 0

    # List threads
    list_res = client_with_clean_db.get("/conversations")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert items[0]["id"] == conv["id"]


def test_dispatch_persists_messages_and_context(client_with_clean_db, monkeypatch):
    """Dispatching commands within a conversation should persist both user and assistant messages."""
    # Mock router to route to general_chat_agent deterministically
    mock_router_result = {
        "agent": "general_chat_agent",
        "confidence": 0.95,
        "reasoning": "Conversational greeting.",
    }
    monkeypatch.setattr("orchestrator_core.core.router._call_groq", lambda cmd: mock_router_result)

    chat_id = f"test-chat-{uuid.uuid4()}"

    # 1. First dispatch with explicit conversation_id
    res1 = client_with_clean_db.post(
        "/dispatch",
        json={"command": "Hello Toji, who are you?", "conversation_id": chat_id},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["agent"] == "general_chat_agent"
    assert data1["metadata"]["conversation_id"] == chat_id

    # 2. Check message history via GET /conversations/{chat_id}/messages
    msg_res = client_with_clean_db.get(f"/conversations/{chat_id}/messages")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert "Hello Toji" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    assert messages[1]["agent"] == "general_chat_agent"

    # 3. Second dispatch without conversation_id auto-creates one
    res2 = client_with_clean_db.post(
        "/dispatch",
        json={"command": "Give me another greeting"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    new_cid = data2["metadata"]["conversation_id"]
    assert new_cid != "test-chat-1"

    # Verify new conversation exists in list
    conv_res = client_with_clean_db.get(f"/conversations/{new_cid}")
    assert conv_res.status_code == 200
    assert conv_res.json()["message_count"] == 2


def test_delete_conversation_cascades(client_with_clean_db):
    """Deleting a conversation thread should delete the record and its messages."""
    # Create conversation
    res = client_with_clean_db.post("/conversations", json={"title": "To Delete"})
    cid = res.json()["id"]

    # Delete
    del_res = client_with_clean_db.delete(f"/conversations/{cid}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Confirm 404
    get_res = client_with_clean_db.get(f"/conversations/{cid}")
    assert get_res.status_code == 404


def test_dispatch_stream_endpoint(client_with_clean_db):
    """POST /dispatch/stream should stream SSE events (meta, token, done) (§5c)."""
    res = client_with_clean_db.post(
        "/dispatch/stream",
        json={"command": "Hello Toji streaming test", "conversation_id": "stream-chat-1"},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    text = res.text
    assert "event: meta" in text
    assert "event: token" in text
    assert "event: done" in text
    assert "general_chat_agent" in text

    # Verify messages saved to SQLite
    msg_res = client_with_clean_db.get("/conversations/stream-chat-1/messages")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"

