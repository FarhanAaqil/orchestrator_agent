"""
orchestrator_core/routes/router_eval.py

Eval routes for the router accuracy harness.

  POST /router/eval        — run the eval on fixed_set.json, store result
  GET  /router/evals       — list all past eval runs from index.json
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from orchestrator_core.storage.db import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/router", tags=["Eval"])

_EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "eval"
_INDEX_PATH = _EVAL_DIR / "index.json"
_DATASET_PATH = _EVAL_DIR / "fixed_set.json"


class EvalSummary(BaseModel):
    run_at: str
    accuracy: float
    correct: int
    total: int
    prompt_hash: str
    stale: bool
    results_file: str | None = None


class EvalListResponse(BaseModel):
    runs: list[EvalSummary]
    total: int


class EvalRunResponse(BaseModel):
    eval_id: str
    status: str
    accuracy: float | None = None
    correct: int | None = None
    total: int | None = None
    stale: bool | None = None
    results_file: str | None = None
    message: str = ""


def _run_eval_and_persist(eval_id: str, db: sqlite3.Connection) -> None:
    """Run the eval harness and write results to DB + index.json."""
    import sys
    eval_root = str(_EVAL_DIR.parent)
    if eval_root not in sys.path:
        sys.path.insert(0, eval_root)

    from eval.run_eval import (
        append_index,
        check_staleness,
        compute_metrics,
        prompt_hash,
        run_classification,
        write_results,
    )

    dataset = json.loads(_DATASET_PATH.read_text())
    _ = check_staleness()
    results = run_classification(dataset)
    metrics = compute_metrics(results)

    ph = prompt_hash()
    results_file = write_results(metrics, results, _DATASET_PATH, dry_run=False)
    append_index(metrics, results_file, dry_run=False)

    # Persist summary to router_eval_runs table
    with db:
        db.execute(
            """
            INSERT INTO router_eval_runs
                (eval_id, total_commands, accuracy, per_agent_json,
                 confusion_matrix_json, model_name, prompt_hash,
                 confidence_threshold, dataset_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eval_id,
                metrics["total"],
                metrics["accuracy"],
                json.dumps(metrics["per_agent"]),
                json.dumps(metrics["confusion_matrix"]),
                "groq_router",
                ph,
                None,
                str(_DATASET_PATH),
            ),
        )

    logger.info("Eval complete — eval_id=%s accuracy=%.2f", eval_id, metrics["accuracy"])


@router.post("/eval", response_model=EvalRunResponse)
async def run_eval(
    background_tasks: BackgroundTasks,
    db: sqlite3.Connection = Depends(get_db_connection),
):
    """
    Trigger a full router eval run.
    Runs synchronously (27 Groq calls) and returns the accuracy.
    """
    import sys
    eval_root = str(_EVAL_DIR.parent)
    if eval_root not in sys.path:
        sys.path.insert(0, eval_root)

    from eval.run_eval import (
        append_index,
        check_staleness,
        compute_metrics,
        prompt_hash,
        run_classification,
        write_results,
    )

    eval_id = str(uuid.uuid4())[:8]
    logger.info("Starting eval run — eval_id=%s", eval_id)

    try:
        dataset = json.loads(_DATASET_PATH.read_text())
        stale = check_staleness()
        results = run_classification(dataset)
        metrics = compute_metrics(results)
        ph = prompt_hash()
        results_file = write_results(metrics, results, _DATASET_PATH, dry_run=False)
        append_index(metrics, results_file, dry_run=False)

        with db:
            db.execute(
                """
                INSERT INTO router_eval_runs
                    (eval_id, total_commands, accuracy, per_agent_json,
                     confusion_matrix_json, model_name, prompt_hash,
                     confidence_threshold, dataset_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (eval_id, metrics["total"], metrics["accuracy"],
                 json.dumps(metrics["per_agent"]),
                 json.dumps(metrics["confusion_matrix"]),
                 "groq_router", ph, None, str(_DATASET_PATH)),
            )

        return EvalRunResponse(
            eval_id=eval_id,
            status="completed",
            accuracy=metrics["accuracy"],
            correct=metrics["correct"],
            total=metrics["total"],
            stale=stale,
            results_file=str(results_file) if results_file else None,
        )
    except Exception as exc:
        logger.exception("Eval run failed — eval_id=%s", eval_id)
        return EvalRunResponse(eval_id=eval_id, status="failed", message=str(exc))


@router.get("/evals", response_model=EvalListResponse)
async def list_evals():
    """List all past eval run summaries from eval/index.json."""
    if not _INDEX_PATH.exists():
        return EvalListResponse(runs=[], total=0)

    try:
        entries = json.loads(_INDEX_PATH.read_text())
    except Exception:
        return EvalListResponse(runs=[], total=0)

    runs = [EvalSummary(**e) for e in entries]
    return EvalListResponse(runs=list(reversed(runs)), total=len(runs))
