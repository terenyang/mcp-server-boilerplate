from fastapi.testclient import TestClient
import pytest

from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as client:
        yield client


def test_root_returns_service_metadata(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["service"]
    assert body["version"]
    assert body["mcp"] == "/mcp"


def test_health_returns_runtime_metrics(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "memory" in body["metrics"]
    assert "mcp" in body["metrics"]


def test_oauth_protected_resource_metadata_is_public(client):
    response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    body = response.json()
    assert body["resource"].endswith("/mcp")
    assert body["authorization_servers"]


def test_mcp_endpoint_requires_authentication(client):
    response = client.get("/mcp")

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
