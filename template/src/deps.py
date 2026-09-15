"""MCP tool dependency functions and the tool_guard decorator.

Usage:
    @mcp.tool()
    @tool_guard(depends_on=[check_entra_groups])
    async def my_tool(param: str) -> str:
        ...

tool_guard runs each dependency in order before the tool body executes.
A dependency that raises will abort the call before the tool body runs.
Tool call logging is triggered inside tool_guard via record_tool_call.
"""
import functools
import logging
from typing import Callable, List, Optional

import config
from src.auth_context import AuthContext, get_auth

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency functions
# ---------------------------------------------------------------------------

async def require_entra_auth(auth: Optional[AuthContext]) -> None:
    """Raise PermissionError if the request was not authenticated via Entra JWT."""
    if not auth or auth.auth_type != "bearer":
        raise PermissionError("Entra ID authentication is required for this tool.")


async def check_entra_groups(auth: Optional[AuthContext]) -> None:
    """Validate that the user belongs to at least one allowed Entra group.

    Reads group Object IDs from the 'groups' claim in the delegated JWT.
    The allowed set is configured via the ALLOWED_ENTRA_GROUPS env var.

    If ALLOWED_ENTRA_GROUPS is empty or not set, the check is skipped and
    any authenticated Entra user is allowed.
    """
    if auth is None:
        raise PermissionError("Missing authentication context")

    if not config.ALLOWED_ENTRA_GROUPS:
        return  # group restriction not configured — any authenticated user is allowed

    user_groups = set(auth.claims.get("groups", []))

    if not user_groups:
        raise PermissionError("No Entra groups found in token")

    if not user_groups.intersection(config.ALLOWED_ENTRA_GROUPS):
        raise PermissionError("User is not authorized to access this tool")


# ---------------------------------------------------------------------------
# Tool call audit hook — replace with your preferred persistence backend
# ---------------------------------------------------------------------------

async def record_tool_call(
    tool_name: str,
    auth: Optional[AuthContext],
    input_summary: Optional[dict] = None,
) -> None:
    """Log a tool invocation for auditing purposes.

    Default implementation logs to the Python logger.
    Replace or extend with your preferred backend (MongoDB, Postgres, etc.).
    Only active in entra_auth mode.
    """
    if config.AUTH_METHOD != "entra_auth":
        return
    upn = auth.user_upn if auth else None
    logger.info("tool_call tool=%s user=%s input=%s", tool_name, upn, input_summary)


# ---------------------------------------------------------------------------
# tool_guard decorator factory
# ---------------------------------------------------------------------------

def tool_guard(depends_on: Optional[List[Callable]] = None):
    """Decorator factory for MCP tools.

    Runs each dependency function in order, then logs the tool call.
    Uses functools.wraps so FastMCP can introspect the original function
    signature via __wrapped__.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            auth = get_auth()
            for dep in (depends_on or []):
                await dep(auth)
            await record_tool_call(fn.__name__, auth, _safe_input_summary(kwargs))
            return await fn(*args, **kwargs)
        return wrapper
    return decorator


def _safe_input_summary(kwargs: dict) -> dict:
    result = {}
    for k, v in kwargs.items():
        try:
            result[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
        except Exception:
            result[k] = "<unserializable>"
    return result
