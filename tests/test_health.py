"""Unit tests for the health check and root endpoints."""

from fastapi.testclient import TestClient


def test_health_check_returns_success(client: TestClient):
    """Verify /health endpoint returns 200 and healthy payload."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "version" in data
    assert "timestamp" in data


def test_root_endpoint_returns_welcome(client: TestClient):
    """Verify root / returns 200 and documentation links."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert data["documentation"] == "/docs"
    assert data["health"] == "/health"
