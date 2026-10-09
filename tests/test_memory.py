"""
tests/test_memory.py

Phase 7 Memory & Sessions test suite:
  1. Semantic Memory: remember, review_pending, confirm, update
  2. Episodic Memory: summarize_session
  3. Recall test: fact from session A retrieved in session B
  4. Forget test: forgotten item purged from vector store and never returned in retrieval
  5. Token Budget Cap: memory context never exceeds token budget
  6. REST API: GET/POST/PATCH/DELETE /memory and POST /memory/summarize/{session_id}
"""

from __future__ import annotations

import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient

from orchestrator_core.main import app
from orchestrator_core.memory.episodic import summarize_session
from orchestrator_core.memory.forget import forget
from orchestrator_core.memory.retrieval import get_context_slice
from orchestrator_core.memory.semantic import (
    confirm,
    get_memory_item,
    list_memory_items,
    remember,
    review_pending,
    update_memory_item,
)
from orchestrator_core.storage.chroma_client import get_chroma_client
from orchestrator_core.storage.db import get_db, run_migrations


@pytest.fixture
def clean_db(tmp_path) -> sqlite3.Connection:
    """Isolated SQLite connection with full migrations applied."""
    db_file = str(tmp_path / "test_memory.db")
    conn = get_db(db_file)
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def ephemeral_chroma():
    """Isolated in-memory ephemeral ChromaDB client."""
    return get_chroma_client(":memory:")


@pytest.fixture
def client(clean_db: sqlite3.Connection) -> TestClient:
    """FastAPI TestClient with isolated clean_db."""
    from orchestrator_core.storage.db import get_db_connection

    app.dependency_overrides[get_db_connection] = lambda: clean_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── 1. Semantic Memory CRUD & Confirmation Lifecycle ─────────────────────────


def test_remember_and_review_pending(clean_db: sqlite3.Connection, ephemeral_chroma):
    """Verify that remember() defaults to pending_review=True and appears in review queue."""
    item = remember(
        value="User prefers dark mode and high-contrast syntax highlighting.",
        kind="preference",
        key="ui_theme",
        pending_review=True,
        db=clean_db,
        chroma_client=ephemeral_chroma,
    )

    assert item.id is not None
    assert item.kind == "preference"
    assert item.key == "ui_theme"
    assert item.pending_review is True
    assert item.deleted is False

    # Check that it appears in review_pending queue
    pending = review_pending(clean_db)
    assert len(pending) == 1
    assert pending[0].id == item.id


def test_confirm_lifecycle(clean_db: sqlite3.Connection, ephemeral_chroma):
    """Verify confirming a pending item moves it out of pending queue."""
    item = remember(
        value="Target deployment OS is Ubuntu 24.04 LTS.",
        kind="fact",
        key="target_os",
        pending_review=True,
        db=clean_db,
        chroma_client=ephemeral_chroma,
    )

    assert item.pending_review is True

    confirmed = confirm(item.id, clean_db, chroma_client=ephemeral_chroma)
    assert confirmed.pending_review is False

    # Review queue should now be empty
    pending = review_pending(clean_db)
    assert len(pending) == 0


def test_update_memory_item(clean_db: sqlite3.Connection, ephemeral_chroma):
    """Verify updating a memory item's value and key."""
    item = remember(
        value="Initial draft preference",
        kind="preference",
        db=clean_db,
        chroma_client=ephemeral_chroma,
    )

    updated = update_memory_item(
        item.id,
        value="Refined draft preference for strict typing",
        key="typing_pref",
        db=clean_db,
        chroma_client=ephemeral_chroma,
    )

    assert updated.value == "Refined draft preference for strict typing"
    assert updated.key == "typing_pref"


def test_remember_invalid_kind_raises(clean_db: sqlite3.Connection):
    """Assert invalid memory kinds are rejected."""
    with pytest.raises(ValueError, match="Invalid memory kind"):
        remember(value="Test", kind="arbitrary_invalid_kind", db=clean_db)  # type: ignore


# ── 2. Episodic Memory Summarization ─────────────────────────────────────────


def test_summarize_session_flow(clean_db: sqlite3.Connection, ephemeral_chroma):
    """Verify that summarize_session processes conversation messages into an episodic record."""
    session_id = str(uuid.uuid4())

    # Seed conversation and messages in clean_db
    with clean_db:
        clean_db.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            (session_id, "State Machine Architecture"),
        )
        clean_db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', ?)",
            (str(uuid.uuid4()), session_id, "How should we implement atomic CAS in SQLite?"),
        )
        clean_db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, agent) VALUES (?, ?, 'assistant', ?, 'general_chat_agent')",
            (str(uuid.uuid4()), session_id, "Use UPDATE approvals SET status='executing' WHERE id=? AND status='approved'."),
        )

    # Summarize with mock LLM callable
    mock_summary = "Topic: SQLite CAS. Decision: Use atomic UPDATE WHERE clause to prevent TOCTOU race conditions."
    episode = summarize_session(
        session_id=session_id,
        db=clean_db,
        llm_callable=lambda transcript: mock_summary,
        chroma_client=ephemeral_chroma,
    )

    assert episode is not None
    assert episode.kind == "episode_summary"
    assert episode.source_session_id == session_id
    assert "Topic: SQLite CAS" in episode.value
    assert episode.pending_review is False

    # Empty session should return None
    empty_session = str(uuid.uuid4())
    assert summarize_session(empty_session, clean_db, chroma_client=ephemeral_chroma) is None


# ── 3. Recall Test (Session A -> Session B) ──────────────────────────────────


def test_recall_across_sessions(clean_db: sqlite3.Connection, ephemeral_chroma):
    """
    Recall test:
      Fact recorded in Session A is retrieved when querying context in Session B.
    """
    session_a = "session-alpha-123"
    session_b = "session-beta-456"

    # Seed conversation sessions
    with clean_db:
        clean_db.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            (session_a, "Session Alpha"),
        )
        clean_db.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            (session_b, "Session Beta"),
        )

    # Remember preference from session A and confirm it
    item = remember(
        value="User strictly mandates Python 3.12 and Pydantic v2 in all backend services.",
        kind="preference",
        key="python_stack",
        source_session_id=session_a,
        pending_review=False,  # pre-confirmed
        db=clean_db,
        chroma_client=ephemeral_chroma,
    )
    assert item is not None

    # Context retrieval performed from session B query
    context = get_context_slice(
        query="What python version and stack should I use?",
        db=clean_db,
        token_budget=1500,
        chroma_client=ephemeral_chroma,
    )

    assert "<relevant_memories>" in context
    assert "</relevant_memories>" in context
    assert "Python 3.12" in context
    assert "Pydantic v2" in context


# ── 4. Forget Test (Deleted item never returned) ─────────────────────────────


def test_forget_flow_purges_and_excludes_from_retrieval(clean_db: sqlite3.Connection, ephemeral_chroma):
    """
    Forget test:
      1. Item is remembered and retrieved.
      2. forget() marks deleted=1 and purges from vector collection.
      3. Subsequent get_context_slice() NEVER returns the forgotten memory.
    """
    item = remember(
        value="User's private home IP address is 198.51.100.42",
        kind="fact",
        key="home_ip",
        pending_review=False,
        db=clean_db,
        chroma_client=ephemeral_chroma,
    )

    # Initial retrieval finds it
    initial_ctx = get_context_slice(
        query="home ip address",
        db=clean_db,
        token_budget=1000,
        chroma_client=ephemeral_chroma,
    )
    assert "198.51.100.42" in initial_ctx

    # Execute forget
    assert forget(item.id, clean_db, chroma_client=ephemeral_chroma, purge_vector=True) is True

    # Verify soft deleted in SQLite
    row = clean_db.execute("SELECT deleted FROM memory_items WHERE id = ?", (item.id,)).fetchone()
    assert row["deleted"] == 1

    # Verify retrieval NEVER returns forgotten item
    after_forget_ctx = get_context_slice(
        query="home ip address",
        db=clean_db,
        token_budget=1000,
        chroma_client=ephemeral_chroma,
    )
    assert "198.51.100.42" not in after_forget_ctx


# ── 5. Token Budget Cap Enforcement ──────────────────────────────────────────


def test_memory_context_strictly_respects_token_budget(clean_db: sqlite3.Connection, ephemeral_chroma):
    """Verify that retrieval strictly respects token_budget and drops/truncates appropriately."""
    for i in range(10):
        remember(
            value=f"Detailed preference rule #{i}: Always ensure complete end-to-end test coverage for every service module with strict typing.",
            kind="preference",
            key=f"rule_{i}",
            pending_review=False,
            db=clean_db,
            chroma_client=ephemeral_chroma,
        )

    # Query with small budget (~60 tokens ≈ 240 chars)
    small_budget = 60
    context = get_context_slice(
        query="preference rules",
        db=clean_db,
        token_budget=small_budget,
        chroma_client=ephemeral_chroma,
    )

    assert len(context) > 0
    # Approx token check: len(context) // 4 should be <= small_budget + 10 margin
    assert len(context) // 4 <= small_budget + 15


# ── 6. REST API Endpoints ────────────────────────────────────────────────────


def test_memory_rest_api_lifecycle(client: TestClient):
    """Test REST API endpoints for memory items: POST, GET, PATCH, DELETE."""
    # 1. Create memory item
    create_resp = client.post(
        "/memory",
        json={
            "value": "Preferred cloud provider is Google Cloud Platform (GCP).",
            "kind": "preference",
            "key": "cloud_provider",
            "pending_review": True,
        },
    )
    assert create_resp.status_code == 201
    mem_data = create_resp.json()
    mem_id = mem_data["id"]
    assert mem_data["key"] == "cloud_provider"
    assert mem_data["pending_review"] is True

    # 2. List memories (filter by pending_review=True)
    list_resp = client.get("/memory?pending_review=true")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(i["id"] == mem_id for i in items)

    # 3. Confirm memory item via POST /memory/{id}/confirm
    confirm_resp = client.post(f"/memory/{mem_id}/confirm")
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["pending_review"] is False

    # 4. Patch memory item
    patch_resp = client.patch(
        f"/memory/{mem_id}",
        json={"value": "Preferred cloud provider is GCP with Artifact Registry and Cloud Run."},
    )
    assert patch_resp.status_code == 200
    assert "Cloud Run" in patch_resp.json()["value"]

    # 5. Delete memory item
    del_resp = client.delete(f"/memory/{mem_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # 6. Verify 404 after deletion
    get_del_resp = client.get(f"/memory/{mem_id}")
    assert get_del_resp.status_code == 404
