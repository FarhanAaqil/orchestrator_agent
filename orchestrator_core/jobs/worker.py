"""
orchestrator_core/jobs/worker.py

Persistent worker process for autonomous jobs (Section 5.4).
Polls for queued jobs via atomic Compare-And-Set claims, executes the ReAct runner,
updates heartbeats, and reaps zombie/crashed jobs.
Supports standalone CLI execution: `python -m orchestrator_core.jobs.worker`.
"""

from __future__ import annotations

import logging
import signal
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Optional

from orchestrator_core.config import get_settings
from orchestrator_core.jobs.reaper import reap_zombies
from orchestrator_core.jobs.service import JobService
from orchestrator_core.storage.db import get_db

logger = logging.getLogger(__name__)


class Worker:
    """
    Background worker daemon polling the persistent jobs queue.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        db_path: Optional[str] = None,
        poll_interval: float = 1.0,
        zombie_timeout: float = 60.0,
        llm_client: Any = None,
        tool_registry: Optional[dict[str, Callable[..., Any]]] = None,
    ) -> None:
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.db_path = db_path or get_settings().database_path
        self.poll_interval = poll_interval
        self.zombie_timeout = zombie_timeout
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def run_once(self, db: Optional[sqlite3.Connection] = None) -> bool:
        """
        Execute a single polling cycle:
          1. Check kill switch
          2. Reap zombie jobs
          3. Claim next queued job
          4. Execute job if claimed
        Returns True if a job was claimed and executed, False if queue was empty.
        """
        own_db = False
        if db is None:
            db = get_db(self.db_path)
            own_db = True

        try:
            # 1. Kill switch check
            row_ks = db.execute("SELECT value FROM system_flags WHERE key = 'kill_switch'").fetchone()
            if row_ks and row_ks["value"].strip().lower() == "on":
                logger.debug("Worker %s: kill switch is active. Skipping job claim.", self.worker_id)
                return False

            # 2. Reap zombies
            reaped = reap_zombies(db, timeout_seconds=self.zombie_timeout)
            if reaped:
                logger.info("Worker %s: reaped %d zombie jobs", self.worker_id, len(reaped))

            # 3. Claim job
            job = JobService.claim_job(self.worker_id, db)
            if job is None:
                return False

            # 4. Execute claimed job
            from orchestrator_core.runner.loop import run_job

            logger.info("Worker %s executing claimed job %s (agent=%s)", self.worker_id, job.id, job.agent)
            run_job(
                job=job,
                db=db,
                llm_client=self.llm_client,
                worker_id=self.worker_id,
                tool_registry=self.tool_registry,
            )
            return True
        finally:
            if own_db:
                db.close()

    def run_forever(self) -> None:
        """Main worker loop running until stopped."""
        logger.info("Worker %s started (polling every %.1fs)", self.worker_id, self.poll_interval)
        while not self._stop_event.is_set():
            try:
                claimed = self.run_once()
                if not claimed:
                    # Sleep only if no work was found
                    self._stop_event.wait(self.poll_interval)
            except Exception as exc:
                logger.exception("Unexpected error in worker loop %s: %s", self.worker_id, exc)
                self._stop_event.wait(self.poll_interval)

        logger.info("Worker %s stopped cleanly.", self.worker_id)

    def start(self) -> None:
        """Start worker in a background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Worker %s is already running.", self.worker_id)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_forever, name=f"worker-{self.worker_id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal worker to stop and wait for completion."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


def main() -> None:
    """CLI entrypoint: python -m orchestrator_core.jobs.worker"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    worker = Worker()

    def handle_signal(sig, frame):
        logger.info("Signal received. Stopping worker...")
        worker.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Starting worker daemon...")
    worker.run_forever()


if __name__ == "__main__":
    main()
