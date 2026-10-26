"""Per-request auth context propagated to MCP tools via contextvars.

Python contextvars propagate through await chains and into asyncio tasks
created via create_task, so a value set in middleware is visible inside
MCPServer tool handlers without any explicit passing.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AuthContext:
    auth_type: str          # "bearer" | "api_key"
    user_oid: Optional[str] = None
    user_name: Optional[str] = None
    user_upn: Optional[str] = None
    claims: Dict[str, Any] = field(default_factory=dict)  # validated JWT payload; empty for API keys


_current_auth: ContextVar[Optional[AuthContext]] = ContextVar(
    "_current_auth", default=None
)


def set_auth(ctx: AuthContext) -> None:
    _current_auth.set(ctx)


def get_auth() -> Optional[AuthContext]:
    return _current_auth.get()
