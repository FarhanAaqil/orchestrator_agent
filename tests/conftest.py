"""
tests/conftest.py

Shared pytest fixtures for the Orchestrator v2 test suite.

All tests use an in-memory SQLite database so they never touch the real
aaqil.db or database/tracker.db files. The fixture runs all migrations
so the full schema is available in each test.
"""

import sqlite3
import pytest

from orchestrator_core.storage.db import get_db, run_migrations


@pytest.fixture()
def db() -> sqlite3.Connection:
    """
    Fresh in-memory SQLite connection with full v2 schema applied.
    Closed automatically after each test.
    """
    conn = get_db(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()
