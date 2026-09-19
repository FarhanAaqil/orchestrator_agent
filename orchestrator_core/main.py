"""
orchestrator_core/main.py

FastAPI composition root for Orchestrator Agent v2.
Initializes the application with lifecycle-managed database migrations,
structured request logging middleware, exception mapping, and health check.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from orchestrator_core.config import get_settings
from orchestrator_core.storage.db import get_db, run_migrations
from orchestrator_core.core.scheduler import start_scheduler, stop_scheduler
from orchestrator_core.exceptions import (
    ApprovalNotFoundError,
    ApprovalNotGrantedError,
    ApprovalExpiredError,
    ApprovalAlreadyExecutedError,
    ApprovalClaimConflictError,
    CircuitOpenError,
    SSRFViolationError,
)
from orchestrator_core.models import ErrorResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager.
    Runs database schema migrations on startup, then starts the scheduler.
    Shuts the scheduler down cleanly on exit.
    """
    conn = get_db()
    try:
        run_migrations(conn)
        logger.info("Database migrations complete.")
    finally:
        conn.close()

    start_scheduler()
    yield
    stop_scheduler()


settings = get_settings()

app = FastAPI(
    title="Orchestrator Agent Core API",
    version=settings.app_version,
    description="v2 Execution engine, approval gate, and multi-agent pipeline orchestrator.",
    lifespan=lifespan,
)


# ── Structured request logging middleware ─────────────────────────────────────

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with command, agent (if present), and latency."""
    request_id = str(uuid.uuid4())[:8]
    t_start = time.monotonic()

    logger.info(
        "[%s] → %s %s",
        request_id, request.method, request.url.path,
    )

    response = await call_next(request)

    latency_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        "[%s] ← %d  latency=%dms",
        request_id, response.status_code, latency_ms,
    )
    return response


# ── Global exception handlers ──────────────────────────────────────────────────

@app.exception_handler(ApprovalNotFoundError)
async def approval_not_found_handler(request: Request, exc: ApprovalNotFoundError):
    return JSONResponse(status_code=404,
        content=ErrorResponse(error="APPROVAL_NOT_FOUND", detail=str(exc)).model_dump())


@app.exception_handler(ApprovalNotGrantedError)
async def approval_not_granted_handler(request: Request, exc: ApprovalNotGrantedError):
    return JSONResponse(status_code=409,
        content=ErrorResponse(error="APPROVAL_NOT_GRANTED", detail=str(exc)).model_dump())


@app.exception_handler(ApprovalExpiredError)
async def approval_expired_handler(request: Request, exc: ApprovalExpiredError):
    return JSONResponse(status_code=410,
        content=ErrorResponse(error="APPROVAL_EXPIRED", detail=str(exc)).model_dump())


@app.exception_handler(ApprovalAlreadyExecutedError)
async def approval_already_executed_handler(request: Request, exc: ApprovalAlreadyExecutedError):
    return JSONResponse(status_code=409,
        content=ErrorResponse(error="APPROVAL_ALREADY_EXECUTED", detail=str(exc)).model_dump())


@app.exception_handler(ApprovalClaimConflictError)
async def approval_claim_conflict_handler(request: Request, exc: ApprovalClaimConflictError):
    return JSONResponse(status_code=409,
        content=ErrorResponse(error="APPROVAL_CLAIM_CONFLICT", detail=str(exc)).model_dump())


@app.exception_handler(CircuitOpenError)
async def circuit_open_handler(request: Request, exc: CircuitOpenError):
    return JSONResponse(status_code=503,
        content=ErrorResponse(error="CIRCUIT_OPEN", detail=str(exc)).model_dump())


@app.exception_handler(SSRFViolationError)
async def ssrf_violation_handler(request: Request, exc: SSRFViolationError):
    return JSONResponse(status_code=400,
        content=ErrorResponse(error="SSRF_VIOLATION", detail=str(exc)).model_dump())


# ── Route registration ────────────────────────────────────────────────────────

from orchestrator_core.dependencies import verify_bearer_token
from orchestrator_core.routes import route as route_module
from orchestrator_core.routes import dispatch as dispatch_module
from orchestrator_core.routes import runs as runs_module
from orchestrator_core.routes import approvals as approvals_module
from orchestrator_core.routes import pipeline as pipeline_module
from orchestrator_core.routes import router_eval as router_eval_module

auth_dependencies = [Depends(verify_bearer_token)]

app.include_router(route_module.router, dependencies=auth_dependencies)
app.include_router(dispatch_module.router, dependencies=auth_dependencies)
app.include_router(runs_module.router, dependencies=auth_dependencies)
app.include_router(approvals_module.router, dependencies=auth_dependencies)
app.include_router(pipeline_module.router, dependencies=auth_dependencies)
app.include_router(router_eval_module.router, dependencies=auth_dependencies)


# ── Health check endpoint ─────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Health check confirming service status, version, and environment."""
    s = get_settings()
    return {"status": "ok", "version": s.app_version, "environment": s.environment}


# ── Static UI / Frontend Serving ──────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
@app.get("/ui", include_in_schema=False)
async def serve_ui():
    """Serve the standalone React 18 / MP072 control plane dashboard."""
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return JSONResponse(status_code=404, content={"error": "UI index.html not found"})

