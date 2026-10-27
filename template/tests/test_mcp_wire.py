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


def _list_tools(client):
    response = client.post("/mcp", headers=MCP_HEADERS, json=rpc("tools/list"))
    return {t["name"]: t for t in parse_rpc(response)["result"]["tools"]}


def test_tools_list_keeps_pre_upgrade_tools_unchanged_except_app_metadata(mcp_client):
    tools = _list_tools(mcp_client)

    assert set(tools) == {"whoami", "ping", "server_profile", "whoami_card"}
    assert all(t["inputSchema"] for t in tools.values())
    # Key order differs between SDK versions; dict equality ignores it.
    baseline = {
        t["name"]: t for t in json.loads(BASELINE.read_text(encoding="utf-8"))["result"]["tools"]
    }
    for name, expected in baseline.items():
        actual = {k: v for k, v in tools[name].items() if k != "_meta"}
        assert actual == expected, name


def test_ping_is_app_callable_and_other_tools_are_not(mcp_client):
    tools = _list_tools(mcp_client)

    assert tools["ping"]["_meta"]["ui"]["visibility"] == ["model", "app"]
    assert "_meta" not in tools["whoami"]
    assert "_meta" not in tools["server_profile"]


def test_whoami_card_tool_references_its_ui_resource(mcp_client):
    tool = _list_tools(mcp_client)["whoami_card"]

    uri = tool["_meta"]["ui"]["resourceUri"]
    assert uri.startswith("ui://")
    assert tool["_meta"]["ui/resourceUri"] == uri


def test_ui_resource_is_listed_and_readable_as_an_app(mcp_client):
    listed = parse_rpc(
        mcp_client.post("/mcp", headers=MCP_HEADERS, json=rpc("resources/list"))
    )["result"]["resources"]
    uris = [r["uri"] for r in listed if r["uri"].startswith("ui://")]
    assert len(uris) == 1

    read = parse_rpc(
        mcp_client.post("/mcp", headers=MCP_HEADERS, json=rpc("resources/read", {"uri": uris[0]}))
    )["result"]["contents"][0]

    assert read["mimeType"] == "text/html;profile=mcp-app"
    assert read["text"].lstrip().lower().startswith("<!doctype html>")
    assert "__APP_BRIDGE__" not in read["text"]
    assert "window.McpApp" in read["text"]


def test_whoami_card_returns_text_and_structured_content(mcp_client):
    result = _call(mcp_client, "whoami_card")

    assert not result.get("isError")
    assert "API key" in result["content"][0]["text"]
    assert result["structuredContent"]["auth_type"] == "api_key"
    assert result["structuredContent"]["user"] is None


def test_whoami_card_for_bearer_caller(mcp_client, monkeypatch):
    result = _bearer_call(mcp_client, monkeypatch, {}, name="whoami_card")

    assert "Jane Doe" in result["content"][0]["text"]
    assert result["structuredContent"]["user"]["upn"] == "jane@corp.com"


def test_restricted_mode_whoami_card_reports_readable_error(mcp_client, restricted_groups):
    result = _call(mcp_client, "whoami_card")

    assert result["isError"] is True
    assert "No Entra groups found in token" in result["content"][0]["text"]


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
