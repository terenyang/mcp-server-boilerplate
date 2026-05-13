"""MCP server — tool definitions.

Add your own tools here following the same @mcp.tool() pattern.
Auth context is available via get_auth() — no need to pass tokens around.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import config
from src.auth_context import get_auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name=config.SERVICE_NAME,
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["*"],
        allowed_origins=["*"],
    ),
)


@mcp.tool()
async def whoami() -> Dict[str, Any]:
    """Return identity information from the current session's access token.

    - OAuth2 Bearer token: returns user claims (name, UPN, OID) from the JWT.
    - API key: returns a message indicating no user token is present.
    """
    auth = get_auth()

    if auth is None or auth.auth_type == "api_key":
        return {
            "auth_type": "api_key",
            "message": "Authenticated via API key — no JWT token available.",
            "user": None,
        }

    return {
        "auth_type": "bearer",
        "user": {
            "oid": auth.user_oid,
            "name": auth.user_name,
            "upn": auth.user_upn,
        },
    }


@mcp.tool()
async def ping(message: str = "ping") -> str:
    """Echo the message back with a server timestamp. Useful as a connectivity check."""
    ts = datetime.now(timezone.utc).isoformat()
    return f"pong: {message!r} at {ts}"


@mcp.tool()
async def server_profile() -> Dict[str, Any]:
    """Return server metadata and extension hints for MCP clients."""
    auth = get_auth()
    auth_type = auth.auth_type if auth else "unknown"

    return {
        "service": {
            "name": config.SERVICE_NAME,
            "owner": config.SERVICE_OWNER,
            "version": config.SERVICE_VERSION,
            "base_url": config.BASE_URL.rstrip("/"),
        },
        "request": {
            "auth_type": auth_type,
            "user": {
                "oid": auth.user_oid,
                "name": auth.user_name,
                "upn": auth.user_upn,
            } if auth and auth.auth_type == "bearer" else None,
        },
        "endpoints": {
            "mcp": "/mcp",
            "health": "/health",
            "oauth_protected_resource": "/.well-known/oauth-protected-resource",
            "oauth_authorization_server": "/.well-known/oauth-authorization-server",
        },
        "extension_points": [
            "Add business tools in src/server.py with @mcp.tool().",
            "Use get_auth() to make tools aware of the authenticated caller.",
            "Keep transport and authentication code inside src/http/.",
        ],
    }
