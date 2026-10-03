"""
orchestrator_core/jobs/events.py

In-memory event hub for SSE streaming of real-time job state transitions and step traces.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

logger = logging.getLogger(__name__)


class JobEventHub:
    """Manages active SSE subscriber queues for job events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all connected subscriber queues."""
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        msg = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

        dead_queues = []
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead_queues.append(q)

        for q in dead_queues:
            self._subscribers.discard(q)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE formatted strings to a client."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                msg = await queue.get()
                yield msg
        finally:
            self._subscribers.discard(queue)


# Global singleton event hub instance
event_hub = JobEventHub()
