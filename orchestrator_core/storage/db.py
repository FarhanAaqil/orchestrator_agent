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
-- 1. Approvals table (atomic state machine storage with SEC-01..08 hardening)
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    target TEXT,
    payload_hash TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'executing', 'executed', 'expired', 'superseded')),
    idempotency_key TEXT UNIQUE,
    approval_signature TEXT,
    approved_hash TEXT,
    supersedes_id TEXT REFERENCES approvals(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP,
    expires_at TIMESTAMP,
    executed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_expires_at ON approvals(expires_at);
CREATE INDEX IF NOT EXISTS idx_approvals_idempotency_key ON approvals(idempotency_key);

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

-- 7. Audit log table (SEC-07: auditable executions and gate transitions)
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    event TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    detail_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);

-- 8. Jobs table (autonomous work units)
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    parent_job_id TEXT REFERENCES jobs(id),
    session_id TEXT REFERENCES conversations(id),
    schedule_id TEXT,
    agent TEXT NOT NULL,
    goal TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN (
        'queued','running','awaiting_approval','awaiting_input',
        'succeeded','failed','cancelled','expired'
    )),
    priority INTEGER NOT NULL DEFAULT 5,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    not_before TIMESTAMP,
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    heartbeat_at TIMESTAMP,
    step_count INTEGER NOT NULL DEFAULT 0,
    max_steps INTEGER NOT NULL DEFAULT 25,
    token_budget INTEGER NOT NULL DEFAULT 60000,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    result_json TEXT,
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(status, priority, not_before);
CREATE INDEX IF NOT EXISTS idx_jobs_thread ON jobs(thread_id);
CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);

-- 9. Job steps table (step-level trace for every LLM/tool/propose/action call)
CREATE TABLE IF NOT EXISTS job_steps (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('llm','tool','propose','note','error')),
    name TEXT,
    input_json TEXT,
    output_json TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    duration_ms INTEGER,
    ok INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, idx)
);
CREATE INDEX IF NOT EXISTS idx_job_steps_job ON job_steps(job_id, idx);

-- 10. System control flags
CREATE TABLE IF NOT EXISTS system_flags (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def run_migrations(conn: sqlite3.Connection) -> None:
    """Execute initial schema migrations creating all required tables and indexes."""
    with conn:
        # Check and migrate columns on existing approvals table if needed before creating indexes
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='approvals';"
        ).fetchone()
        if table_exists:
            cur = conn.execute("PRAGMA table_info(approvals);")
            columns = [row[1] for row in cur.fetchall()]
            if "target" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN target TEXT;")
            if "payload_hash" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN payload_hash TEXT;")
            if "idempotency_key" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN idempotency_key TEXT;")
            if "approval_signature" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN approval_signature TEXT;")
            if "approved_hash" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN approved_hash TEXT;")
            if "supersedes_id" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN supersedes_id TEXT REFERENCES approvals(id);")
            if "decided_at" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN decided_at TIMESTAMP;")

        conn.executescript(SCHEMA_SQL)

        # Seed system control flags if not already present
        conn.execute(
            "INSERT OR IGNORE INTO system_flags (key, value) VALUES ('kill_switch', 'off');"
        )
        conn.execute(
            "INSERT OR IGNORE INTO system_flags (key, value) VALUES ('daily_budget_usd', '5.00');"
        )


def log_audit(
    db: sqlite3.Connection,
    actor: str,
    event: str,
    entity: str = "approval",
    entity_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> str:
    """Insert an immutable record into the audit_log table (SEC-07)."""
    import json
    import uuid
    from datetime import datetime, timezone

    audit_id = str(uuid.uuid4())
    detail_json = json.dumps(detail or {}, separators=(",", ":"), sort_keys=True)
    created_at = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute(
            """
            INSERT INTO audit_log (id, actor, event, entity, entity_id, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (audit_id, actor, event, entity, entity_id, detail_json, created_at),
        )
    return audit_id


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

    # Ensure schema is initialized if tables do not exist yet
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='approvals';")
    if not cur.fetchone():
        run_migrations(conn)

    return conn


def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a managed SQLite connection."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()

