"""Shared fixtures: the real ASGI app driven over HTTP with API-key auth."""
import json

import pytest
from fastapi.testclient import TestClient

import config
from main import app

API_KEY = "test-key"
MCP_HEADERS = {
    "x-api-key": API_KEY,
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}
INIT_PARAMS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "pytest", "version": "0"},
}


def rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        body["params"] = params
    return body


def parse_rpc(response) -> dict:
    """Return the JSON-RPC message from a JSON or SSE response body."""
    text = response.text
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(text)


@pytest.fixture(scope="session")
def mcp_client():
    """Single TestClient for the whole session, with the lifespan running.

    The MCP session manager's run() can only be entered once per process, so
    every test module must share this client instead of opening its own.
    """
    original = config.API_KEYS
    config.API_KEYS = API_KEY
    try:
        with TestClient(app) as client:
            yield client
    finally:
        config.API_KEYS = original


@pytest.fixture
def restricted_groups(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_ENTRA_GROUPS", {"group-1"})
