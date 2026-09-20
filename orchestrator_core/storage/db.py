"""
orchestrator_core/storage/db.py

SQLite connection factory and schema migration runner.
Provides dependency-injectable database connections with WAL mode and foreign key enforcement.
"""

import os
import sqlite3
from typing import Generator, Optional
from orchestrator_core.config import get_settings


SCHEMA_SQL = """
-- 1. Approvals table (atomic state machine storage)
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'executing', 'executed', 'expired')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    executed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_expires_at ON approvals(expires_at);

-- 2. Pipeline runs table
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);

-- 3. Pipeline steps table
CREATE TABLE IF NOT EXISTS pipeline_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_steps_run_id ON pipeline_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_steps_run_order ON pipeline_steps(run_id, step_number);

-- 4. Router eval runs table
CREATE TABLE IF NOT EXISTS router_eval_runs (
    eval_id TEXT PRIMARY KEY,
    total_commands INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    per_agent_json TEXT NOT NULL,
    confusion_matrix_json TEXT NOT NULL,
    model_name TEXT NOT NULL,
    prompt_hash TEXT,
    code_commit TEXT,
    confidence_threshold REAL,
    dataset_version TEXT,
    run_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_router_eval_runs_run_at ON router_eval_runs(run_at);

-- 5. Conversations table (multi-chat sessions)
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at);

-- 6. Messages table (persistent multi-turn message history)
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    agent TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
"""


def get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create and configure a new SQLite connection."""
    if db_path is None:
        db_path = get_settings().database_path

    # In-memory database or path on filesystem
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enforce SQLite best practices: foreign keys, busy timeout, and WAL mode
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -64000;")
        conn.execute("PRAGMA temp_store = MEMORY;")

    return conn


def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a managed SQLite connection."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def run_migrations(conn: sqlite3.Connection) -> None:
    """Execute initial schema migrations creating all required tables and indexes."""
    with conn:
        conn.executescript(SCHEMA_SQL)
