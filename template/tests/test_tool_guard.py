import logging

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from src.auth_context import AuthContext, set_auth
from src.deps import tool_guard


async def _deny(auth):
    raise PermissionError("No Entra groups found in token")


@pytest.mark.asyncio
async def test_dependency_error_becomes_tool_error_with_same_text(caplog):
    set_auth(AuthContext(auth_type="api_key"))

    @tool_guard(depends_on=[_deny])
    async def guarded() -> str:
        return "ran"

    with caplog.at_level(logging.WARNING, logger="src.deps"):
        with pytest.raises(ToolError, match="No Entra groups found in token") as info:
            await guarded()

    assert isinstance(info.value.__cause__, PermissionError)
    record = next(r for r in caplog.records if "guarded" in r.getMessage())
    assert record.exc_info is not None


@pytest.mark.asyncio
async def test_tool_body_error_becomes_tool_error():
    set_auth(AuthContext(auth_type="api_key"))

    @tool_guard()
    async def boom() -> str:
        raise ValueError("bad input")

    with pytest.raises(ToolError, match="bad input"):
        await boom()


@pytest.mark.asyncio
async def test_existing_tool_error_is_not_rewrapped():
    set_auth(AuthContext(auth_type="api_key"))
    original = ToolError("already friendly")

    @tool_guard()
    async def raises_tool_error() -> str:
        raise original

    with pytest.raises(ToolError) as info:
        await raises_tool_error()

    assert info.value is original
