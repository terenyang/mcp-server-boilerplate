"""MCP server — tool definitions.

Add your own tools here following the same @mcp.tool() pattern.
Auth context is available via get_auth() — no need to pass tokens around.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import config
from src.apps import APP_CALLABLE_META, apps
from src.auth_context import get_auth
from src.deps import check_entra_groups,tool_guard
from src.identity import identity_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Transport settings (path, stateless mode, security) are passed to
# streamable_http_app() in src/http/mcp_mount.py — mcp 2.x moved them off the
# constructor.
# Extensions are fixed at construction: `apps` was fully populated when
# src.apps was imported above, so anything registered after this line is ignored.
mcp = MCPServer(
    name=config.SERVICE_NAME,
    extensions=[apps] if config.ENABLE_MCP_APPS else [],
)

# Must be passed explicitly: when omitted, mcp 2.x auto-enables DNS rebinding
# protection that only allows localhost hosts, which rejects tunnels and public
# domains. Authentication remains the access control.
MCP_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
    allowed_hosts=["*"],
    allowed_origins=["*"],
)


@mcp.tool()
@tool_guard(depends_on=[check_entra_groups])
async def whoami() -> Dict[str, Any]:
    """Return identity information from the current session's access token.

    - OAuth2 Bearer token: returns user claims (name, UPN, OID) from the JWT.
    - API key: returns a message indicating no user token is present.
    """
    return identity_info()


@mcp.tool(meta=APP_CALLABLE_META)  # the whoami_card app calls ping through the host
@tool_guard(depends_on=[check_entra_groups])
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
