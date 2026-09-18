# BASELINE — Orchestrator Agent v2 Rewrite Reference

## Pre-rewrite commit hash
```
d558406  fix(deploy): add packages.txt and remove pyaudio for Streamlit Cloud Linux compatibility
```
This is the last commit of the v1 codebase before the v2 rewrite began.
Tag: `v1-archive` points to this commit.

## v2 rewrite started at
```
6535be7  Add New plan/ to gitignore along with runtime artifacts and WAL files
```
Date: 2026-09-13

## Branch
All v2 work lands on `master`.

## Git history purge (GATED — run only after Phases 0-4 are green)
Paths to purge from history:
- `aaqil.db`
- `chroma_db/`
- `database/tracker.db`

Command (run on a fresh clone, not in-place):
```bash
pip install git-filter-repo
git filter-repo --path aaqil.db --path chroma_db --path database/tracker.db --invert-paths
git log --all --full-history -- aaqil.db chroma_db/ database/tracker.db  # must be empty
```

Pre-purge backup: keep local zip archive until verified.

## Verification log
- [x] Phase 0 complete (Safety baseline established, bypass tools removed, .env.example created)
- [x] Phase 1 complete (FastAPI core, lazy config, SQLite migrations, scoped ChromaDB, GET /health verified)
- [x] Phase 2 complete (router eval harness, fixed dataset of 54 commands, confusion matrix renderer, router eval routes)
- [x] Phase 3 complete (approval gate tests, concurrency, SDK isolation, 29 passing unit & integration tests)
- [x] Phase 4 complete (CI green)
- [ ] History purge executed and verified
- [ ] Pre-purge backup deleted only after verified

## Day 7 Baseline — CI, Quarantine, Dockerfile, Auth Boundary
- Quarantined 6 legacy v1 modules into `experimental/` (`linkedin_agent`, `job_search_agent`, `github_agent`, `project_manager_agent`, `info_agent`, `voice_io`) with `NOT_SUPPORTED.md` boundaries.
- Bearer-token authentication dependency implemented in `orchestrator_core/dependencies.py` and applied to all non-health routes in `orchestrator_core/main.py`.
- Dockerfile hardened with multi-stage build, non-root user (`appuser`), and healthcheck.
- `.dockerignore` updated to strictly exclude experimental, planning, and evaluation artifacts.
- GitHub Actions CI workflow implemented in `.github/workflows/ci.yml` with ruff linting, zero experimental imports check, zero SDK leakage check, and full test suite execution.
- Full pytest suite: 34 passed in 1.8s (including 5 auth boundary unit tests).
- CI Badge: `![CI](https://github.com/FarhanAaqil/orchestrater_agent/actions/workflows/ci.yml/badge.svg)`

## FastAPI Core Startup Smoke Test (Phase 1)
- Verified `uvicorn orchestrator_core.main:app` imports with zero side effects.
- SQLite schema migrations execute automatically in lifespan handler.
- Endpoint `GET /health` responds `200 OK` with `{"status": "ok", "version": "2.0.0-alpha", "environment": "development"}`.

## Test Suite Baseline (Day 6 / Phase 3)
- Full pytest suite: 29 passed in 1.3s
- Coverage areas: approval state machine, CAS claim concurrency, replay prevention, mid-crash reconciliation, SDK isolation static AST checks, router classification & clarification, circuit breaker fail-fast & recovery, and pipeline step auditing.
- Mutation verification: manual status check disabling confirmed 3 red failures, cleanly restored to green.
