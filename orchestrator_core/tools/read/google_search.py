"""
orchestrator_core/tools/read/google_search.py

Google Programmable Search JSON API integration (Capability.READ).
Features:
  1. 24-hour persistent SQLite results cache.
  2. Daily quota tracking in system_flags with configurable ceiling.
  3. Circuit breaker protection against Google API outages.
  4. Graceful fallback to DuckDuckGo when quota is exhausted or credentials are unset.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests
from pydantic import BaseModel, Field

from orchestrator_core.config import get_settings
from orchestrator_core.core.circuit_breaker import CircuitBreaker
from orchestrator_core.storage.db import get_db

logger = logging.getLogger(__name__)

# Daily free tier quota limit for Google CSE
DEFAULT_DAILY_QUOTA = 100

# Circuit breaker for Google Search API
_google_search_breaker = CircuitBreaker(
    service="google_search_api",
    failure_threshold=3,
    cooldown_seconds=60.0,
)


class GoogleSearchArgs(BaseModel):
    """Arguments for google_search tool."""
    query: str = Field(description="Search query keywords.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of search results to retrieve.")


def _init_cache_table(db: sqlite3.Connection) -> None:
    """Ensure google_search_cache table exists."""
    with db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS google_search_cache (
                query_hash TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_google_search_cache_created ON google_search_cache(created_at);"
        )


def _get_cached_results(query: str, db: sqlite3.Connection) -> Optional[list[dict[str, str]]]:
    """Retrieve search results from cache if under 24 hours old."""
    _init_cache_table(db)
    q_hash = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()
    row = db.execute(
        "SELECT results_json, created_at FROM google_search_cache WHERE query_hash = ?",
        (q_hash,),
    ).fetchone()

    if not row:
        return None

    try:
        created_at = datetime.fromisoformat(row["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except Exception:
        created_at = datetime.now(timezone.utc) - timedelta(days=2)

    now = datetime.now(timezone.utc)
    if (now - created_at) < timedelta(hours=24):
        logger.info("[google_search] Cache hit for query: '%s'", query)
        try:
            return json.loads(row["results_json"])
        except Exception:
            return None

    return None


def _set_cached_results(query: str, results: list[dict[str, str]], db: sqlite3.Connection) -> None:
    """Store search results in SQLite 24h cache."""
    _init_cache_table(db)
    q_hash = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute(
            """
            INSERT INTO google_search_cache (query_hash, query, results_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(query_hash) DO UPDATE SET results_json = excluded.results_json, created_at = excluded.created_at
            """,
            (q_hash, query.strip(), json.dumps(results, separators=(",", ":")), now_iso),
        )


def _check_and_increment_quota(db: sqlite3.Connection) -> bool:
    """Check daily quota in system_flags and increment count. Returns True if within quota."""
    today_key = f"google_search_quota_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    row = db.execute("SELECT value FROM system_flags WHERE key = ?", (today_key,)).fetchone()
    count = int(row["value"]) if row else 0

    if count >= DEFAULT_DAILY_QUOTA:
        logger.warning("[google_search] Daily quota exhausted (%d/%d).", count, DEFAULT_DAILY_QUOTA)
        return False

    new_count = count + 1
    now_iso = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute(
            """
            INSERT INTO system_flags (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (today_key, str(new_count), now_iso),
        )
    return True


def _fallback_ddg_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Fallback search using DuckDuckGo."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                })
        return results
    except Exception as exc:
        logger.warning("[google_search] DDG fallback failed: %s", exc)
        return [{"title": "Search Unavailable", "snippet": f"Search provider error: {exc}", "url": ""}]


def google_search(query: str, max_results: int = 5, db: Optional[sqlite3.Connection] = None) -> list[dict[str, str]]:
    """
    Search web using Google Custom Search with 24h cache, quota tracking, and DDG fallback.
    """
    own_db = False
    if db is None:
        db = get_db(get_settings().database_path)
        own_db = True

    try:
        # 1. Check 24-hour persistent cache
        cached = _get_cached_results(query, db)
        if cached is not None:
            return cached[:max_results]

        # 2. Check credentials
        api_key = os.getenv("GOOGLE_SEARCH_API_KEY") or os.getenv("GOOGLE_API_KEY")
        cx = os.getenv("GOOGLE_SEARCH_CX") or os.getenv("GOOGLE_CSE_ID")

        if not api_key or not cx:
            logger.info("[google_search] Missing Google API key or CX. Using DuckDuckGo fallback.")
            results = _fallback_ddg_search(query, max_results)
            _set_cached_results(query, results, db)
            return results

        # 3. Check quota in system_flags
        if not _check_and_increment_quota(db):
            logger.info("[google_search] Daily quota reached. Using DuckDuckGo fallback.")
            results = _fallback_ddg_search(query, max_results)
            _set_cached_results(query, results, db)
            return results

        # 4. Check circuit breaker
        if not _google_search_breaker.can_execute():
            logger.warning("[google_search] Circuit breaker open for Google CSE. Using DDG fallback.")
            return _fallback_ddg_search(query, max_results)

        # 5. Execute Google Custom Search call
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": api_key,
                "cx": cx,
                "q": query,
                "num": min(max(1, max_results), 10),
            }
            resp = requests.get(url, params=params, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                results = [
                    {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "url": item.get("link", ""),
                    }
                    for item in items
                ]
                _google_search_breaker.record_success()
                _set_cached_results(query, results, db)
                return results
            else:
                logger.warning("[google_search] Google CSE returned status %d: %s", resp.status_code, resp.text[:150])
                _google_search_breaker.record_failure()
                return _fallback_ddg_search(query, max_results)
        except Exception as exc:
            logger.warning("[google_search] Google API call error (%s). Falling back to DDG.", exc)
            _google_search_breaker.record_failure()
            return _fallback_ddg_search(query, max_results)
    finally:
        if own_db:
            db.close()
