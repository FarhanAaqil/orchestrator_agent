# Multi-stage Dockerfile for Orchestrator Agent v2 Core Service

# ── Stage 1: Build dependencies ──
FROM python:3.11-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime image ──
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/appuser/.local/bin:$PATH"

# Create non-root user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

# Copy installed dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy only production core source code and database dir
COPY --chown=appuser:appgroup orchestrator_core/ /app/orchestrator_core/
COPY --chown=appuser:appgroup database/ /app/database/

# Create database and runtime directories with correct permissions
RUN mkdir -p /app/database && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "orchestrator_core.main:app", "--host", "0.0.0.0", "--port", "8000"]