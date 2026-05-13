import pytest

from src.auth_context import AuthContext, set_auth
from src.server import ping, server_profile, whoami


@pytest.mark.asyncio
async def test_ping_includes_message():
    result = await ping("hello")

    assert "pong" in result
    assert "hello" in result


@pytest.mark.asyncio
async def test_whoami_supports_api_key_context():
    set_auth(AuthContext(auth_type="api_key"))

    result = await whoami()

    assert result["auth_type"] == "api_key"
    assert result["user"] is None


@pytest.mark.asyncio
async def test_server_profile_reports_auth_type():
    set_auth(AuthContext(auth_type="api_key"))

    result = await server_profile()

    assert result["request"]["auth_type"] == "api_key"
    assert result["endpoints"]["mcp"] == "/mcp"
