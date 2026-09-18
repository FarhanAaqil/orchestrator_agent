"""
tests/test_auth.py

Unit and integration tests for bearer token authentication boundary.
Verifies that:
  - Health endpoint is always publicly accessible.
  - When AUTH_TOKEN is unset, routes remain accessible in development.
  - When AUTH_TOKEN is configured, non-health routes require a valid Bearer token.
  - Invalid or missing tokens return 401 Unauthorized.
"""

import pytest
from fastapi.testclient import TestClient
from orchestrator_core.main import app
from orchestrator_core.config import Settings, get_settings


def test_health_check_always_accessible_without_auth(monkeypatch):
    """GET /health must never require authentication."""
    test_settings = Settings(auth_token="super-secret-token")
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        client = TestClient(app)
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_routes_open_when_auth_token_unset(monkeypatch):
    """When no auth token is configured, requests proceed without 401."""
    test_settings = Settings(auth_token=None)
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        client = TestClient(app)
        # Hit /approvals with no Authorization header
        res = client.get("/approvals")
        # Should not be 401 Unauthorized (should be 200)
        assert res.status_code == 200
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_protected_route_rejects_missing_auth_when_token_set():
    """When auth_token is configured, requests without token receive 401."""
    test_settings = Settings(auth_token="secret-production-token")
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        client = TestClient(app)
        res = client.get("/approvals")
        assert res.status_code == 401
        assert "Authorization header" in res.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_protected_route_rejects_invalid_token():
    """Requests with wrong bearer token receive 401."""
    test_settings = Settings(auth_token="secret-production-token")
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        client = TestClient(app)
        headers = {"Authorization": "Bearer invalid-token-value"}
        res = client.get("/approvals", headers=headers)
        assert res.status_code == 401
        assert "Invalid authentication token" in res.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_protected_route_accepts_valid_token():
    """Requests with matching bearer token succeed."""
    test_settings = Settings(auth_token="secret-production-token")
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        client = TestClient(app)
        headers = {"Authorization": "Bearer secret-production-token"}
        res = client.get("/approvals", headers=headers)
        assert res.status_code == 200
    finally:
        app.dependency_overrides.pop(get_settings, None)
