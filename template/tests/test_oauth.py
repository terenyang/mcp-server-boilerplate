"""OAuth discovery and Entra proxy behavior, without a real Entra tenant."""
import urllib.parse

import pytest

import config

CLIENT_ID = "11111111-2222-3333-4444-555555555555"


def _query(location: str) -> dict:
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(location).query, keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}


@pytest.fixture
def entra_app(monkeypatch):
    monkeypatch.setattr(config, "AZURE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(config, "REQUIRED_SCOPE", "MCP.Access")


# --- protected-resource metadata and 401 challenge --------------------------

def test_protected_resource_metadata_bare_and_suffixed_are_identical(mcp_client):
    bare = mcp_client.get("/.well-known/oauth-protected-resource")
    suffixed = mcp_client.get("/.well-known/oauth-protected-resource/mcp")

    assert bare.status_code == 200
    assert suffixed.status_code == 200
    assert suffixed.json() == bare.json()
    assert bare.json()["resource"].endswith("/mcp")
    assert bare.json()["authorization_servers"] == [config.BASE_URL.rstrip("/")]


def test_unauthenticated_mcp_request_is_challenged_with_suffixed_metadata_url(mcp_client):
    response = mcp_client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response.status_code == 401
    expected = (
        f'Bearer resource_metadata="{config.BASE_URL.rstrip("/")}'
        '/.well-known/oauth-protected-resource/mcp"'
    )
    assert response.headers["WWW-Authenticate"] == expected


# --- /authorize -------------------------------------------------------------

def test_authorize_normalizes_scopes(mcp_client, entra_app):
    response = mcp_client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "dynamic-x",
            "redirect_uri": "http://localhost/cb",
            "state": "s1",
            "scope": "MCP.Access openid",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    scopes = _query(response.headers["location"])["scope"].split()
    full = f"api://{CLIENT_ID}/MCP.Access"
    assert scopes.count(full) == 1
    assert "MCP.Access" not in scopes
    assert "openid" in scopes
    assert "offline_access" in scopes


# --- /token -----------------------------------------------------------------

class _FakeEntraResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def _patch_entra_token(monkeypatch, status_code, body):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None, headers=None, timeout=None):
            return _FakeEntraResponse(status_code, body)

    monkeypatch.setattr("src.http.oauth_proxy.httpx.AsyncClient", FakeAsyncClient)


def test_token_success_adds_resource(mcp_client, monkeypatch):
    _patch_entra_token(
        monkeypatch, 200, {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}
    )

    response = mcp_client.post(
        "/token", data={"grant_type": "authorization_code", "code": "c", "client_id": "dynamic-x"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "at"
    assert body["resource"] == f"{config.BASE_URL.rstrip('/')}/mcp"


def test_token_error_is_passed_through_without_resource(mcp_client, monkeypatch):
    error = {"error": "invalid_grant", "error_description": "expired"}
    _patch_entra_token(monkeypatch, 400, error)

    response = mcp_client.post(
        "/token", data={"grant_type": "authorization_code", "code": "c", "client_id": "dynamic-x"}
    )

    assert response.status_code == 400
    assert response.json() == error


# --- /register ----------------------------------------------------------------

def test_register_echoes_requested_grant_types(mcp_client):
    grants = ["authorization_code", "refresh_token"]

    response = mcp_client.post(
        "/register", json={"redirect_uris": ["http://localhost/cb"], "grant_types": grants}
    )

    assert response.status_code == 201
    assert response.json()["grant_types"] == grants


def test_register_defaults_grant_types(mcp_client):
    response = mcp_client.post("/register", json={"redirect_uris": ["http://localhost/cb"]})

    assert response.status_code == 201
    assert response.json()["grant_types"] == ["authorization_code"]


# --- /authorize state -----------------------------------------------------------

_AUTHORIZE_BASE = {
    "response_type": "code",
    "client_id": "dynamic-x",
    "redirect_uri": "http://localhost/cb",
}


def test_authorize_works_without_state(mcp_client, entra_app):
    response = mcp_client.get("/authorize", params=_AUTHORIZE_BASE, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://login.microsoftonline.com/")
    assert _query(response.headers["location"])["state"] == ""


def test_authorize_forwards_supplied_state(mcp_client, entra_app):
    response = mcp_client.get(
        "/authorize", params={**_AUTHORIZE_BASE, "state": "abc123"}, follow_redirects=False
    )

    assert response.status_code == 302
    assert _query(response.headers["location"])["state"] == "abc123"
