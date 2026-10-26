"""Wire-level tests: JSON-RPC over HTTP against the real ASGI app."""
import json
import logging
from pathlib import Path

from tests.conftest import INIT_PARAMS, MCP_HEADERS, parse_rpc, rpc

BASELINE = Path(__file__).parent / "fixtures" / "tools_list_baseline.json"


def test_health_through_app(mcp_client):
    assert mcp_client.get("/health").status_code == 200


def test_initialize_at_mcp_without_slash(mcp_client):
    response = mcp_client.post("/mcp", headers=MCP_HEADERS, json=rpc("initialize", INIT_PARAMS))

    assert response.status_code == 200
    assert "serverInfo" in parse_rpc(response)["result"]


def test_initialize_at_mcp_with_slash(mcp_client):
    response = mcp_client.post("/mcp/", headers=MCP_HEADERS, json=rpc("initialize", INIT_PARAMS))

    assert response.status_code == 200
    assert "serverInfo" in parse_rpc(response)["result"]


def test_mcp_does_not_redirect(mcp_client):
    response = mcp_client.post(
        "/mcp", headers=MCP_HEADERS, json=rpc("initialize", INIT_PARAMS), follow_redirects=False
    )

    assert response.status_code == 200


def test_doubled_path_is_not_the_endpoint(mcp_client):
    response = mcp_client.post("/mcp/mcp", headers=MCP_HEADERS, json=rpc("initialize", INIT_PARAMS))

    assert response.status_code == 404


def test_public_host_header_is_accepted(mcp_client):
    headers = {**MCP_HEADERS, "host": "example.devtunnels.ms"}

    response = mcp_client.post("/mcp", headers=headers, json=rpc("initialize", INIT_PARAMS))

    assert response.status_code == 200


def test_tool_call_without_prior_initialize(mcp_client):
    response = mcp_client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json=rpc("tools/call", {"name": "ping", "arguments": {"message": "hi"}}),
    )

    assert response.status_code == 200
    result = parse_rpc(response)["result"]
    assert not result.get("isError")
    assert "pong" in json.dumps(result)


def test_tools_list_matches_pre_upgrade_baseline(mcp_client):
    response = mcp_client.post("/mcp", headers=MCP_HEADERS, json=rpc("tools/list"))

    tools = parse_rpc(response)["result"]["tools"]
    assert {t["name"] for t in tools} == {"whoami", "ping", "server_profile"}
    assert all(t["inputSchema"] for t in tools)
    # Key order differs between SDK versions; dict equality ignores it.
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["result"]["tools"]
    assert sorted(tools, key=lambda t: t["name"]) == sorted(baseline, key=lambda t: t["name"])


def _call(client, name, arguments=None):
    response = client.post(
        "/mcp", headers=MCP_HEADERS, json=rpc("tools/call", {"name": name, "arguments": arguments or {}})
    )
    assert response.status_code == 200
    return parse_rpc(response)["result"]


def test_restricted_mode_whoami_reports_readable_error(mcp_client, restricted_groups):
    result = _call(mcp_client, "whoami")

    assert result["isError"] is True
    assert "No Entra groups found in token" in result["content"][0]["text"]


def test_restricted_mode_ping_is_guarded(mcp_client, restricted_groups):
    result = _call(mcp_client, "ping", {"message": "x"})

    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "No Entra groups found in token" in text
    assert "pong" not in text


def test_guarded_failure_logs_warning_with_traceback(mcp_client, restricted_groups, caplog):
    with caplog.at_level(logging.WARNING, logger="src.deps"):
        _call(mcp_client, "ping")

    record = next(r for r in caplog.records if "ping" in r.getMessage())
    assert record.exc_info is not None


def test_argument_validation_error_is_visible(mcp_client):
    result = _call(mcp_client, "ping", {"message": {"not": "a string"}})

    assert result["isError"] is True
    assert "message" in result["content"][0]["text"]


def _bearer_call(client, monkeypatch, claims, name="whoami"):
    async def fake_authenticate(token):
        return "oid-1", "Jane Doe", "jane@corp.com", claims

    monkeypatch.setattr("src.http.middleware.auth.authenticate", fake_authenticate)
    headers = {k: v for k, v in MCP_HEADERS.items() if k != "x-api-key"}
    headers["authorization"] = "Bearer fake-token"
    response = client.post(
        "/mcp", headers=headers, json=rpc("tools/call", {"name": name, "arguments": {}})
    )
    assert response.status_code == 200
    return parse_rpc(response)["result"]


def test_bearer_user_in_allowed_group_can_call_tool(mcp_client, restricted_groups, monkeypatch):
    result = _bearer_call(mcp_client, monkeypatch, {"groups": ["group-1", "other"]})

    assert not result.get("isError")
    assert "Jane Doe" in json.dumps(result)


def test_bearer_user_not_in_allowed_group_is_denied(mcp_client, restricted_groups, monkeypatch):
    result = _bearer_call(mcp_client, monkeypatch, {"groups": ["other"]})

    assert result["isError"] is True
    assert "User is not authorized to access this tool" in result["content"][0]["text"]


def test_bearer_token_without_groups_claim_is_denied(mcp_client, restricted_groups, monkeypatch):
    result = _bearer_call(mcp_client, monkeypatch, {})

    assert result["isError"] is True
    assert "No Entra groups found in token" in result["content"][0]["text"]
