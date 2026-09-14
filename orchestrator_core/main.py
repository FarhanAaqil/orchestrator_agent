"""
orchestrator_core/main.py

FastAPI composition root for Orchestrator Agent v2.
Initializes the application with lifecycle-managed database migrations,
exception mapping, and core health check endpoint.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from orchestrator_core.config import get_settings
from orchestrator_core.storage.db import get_db, run_migrations
from orchestrator_core.exceptions import (
    ApprovalNotFoundError,
    ApprovalNotGrantedError,
    ApprovalExpiredError,
    ApprovalAlreadyExecutedError,
    ApprovalClaimConflictError,
    CircuitOpenError,
)
from orchestrator_core.models import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager.
    Runs database schema migrations on startup with no import-time side effects.
    """
    # 1. Startup: initialize database schema
    conn = get_db()
    try:
        run_migrations(conn)
    finally:
        conn.close()

    yield

    # 2. Shutdown: clean up any active resources if needed


settings = get_settings()

app = FastAPI(
    title="Orchestrator Agent Core API",
    version=settings.app_version,
    description="v2 Execution engine, approval gate, and multi-agent pipeline orchestrator.",
    lifespan=lifespan,
)


# ── Global exception handlers ──────────────────────────────────────────────────

@app.exception_handler(ApprovalNotFoundError)
async def approval_not_found_handler(request: Request, exc: ApprovalNotFoundError):
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(error="APPROVAL_NOT_FOUND", detail=str(exc)).model_dump(),
    )


@app.exception_handler(ApprovalNotGrantedError)
async def approval_not_granted_handler(request: Request, exc: ApprovalNotGrantedError):
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(error="APPROVAL_NOT_GRANTED", detail=str(exc)).model_dump(),
    )


@app.exception_handler(ApprovalExpiredError)
async def approval_expired_handler(request: Request, exc: ApprovalExpiredError):
    return JSONResponse(
        status_code=410,
        content=ErrorResponse(error="APPROVAL_EXPIRED", detail=str(exc)).model_dump(),
    )


@app.exception_handler(ApprovalAlreadyExecutedError)
async def approval_already_executed_handler(request: Request, exc: ApprovalAlreadyExecutedError):
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(error="APPROVAL_ALREADY_EXECUTED", detail=str(exc)).model_dump(),
    )


@app.exception_handler(ApprovalClaimConflictError)
async def approval_claim_conflict_handler(request: Request, exc: ApprovalClaimConflictError):
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(error="APPROVAL_CLAIM_CONFLICT", detail=str(exc)).model_dump(),
    )


@app.exception_handler(CircuitOpenError)
async def circuit_open_handler(request: Request, exc: CircuitOpenError):
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(error="CIRCUIT_OPEN", detail=str(exc)).model_dump(),
    )


# ── Health check endpoint ─────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint confirming service status, version, and environment."""
    current_settings = get_settings()
    return {
        "status": "ok",
        "version": current_settings.app_version,
        "environment": current_settings.environment,
    }
