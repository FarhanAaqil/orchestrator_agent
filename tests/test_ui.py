"""
tests/test_ui.py

Tests for UI endpoint serving and static assets in Orchestrator Agent v2.
"""

from fastapi.testclient import TestClient

from orchestrator_core.main import app


def test_ui_root_serves_html():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Orchestrator Agent" in response.text
    assert 'id="root"' in response.text


def test_ui_path_serves_html():
    client = TestClient(app)
    response = client.get("/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Orchestrator Agent" in response.text
