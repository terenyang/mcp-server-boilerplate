"""OAuth 2.0 discovery endpoints for MCP authorization.

Two well-known endpoints:

1. /.well-known/oauth-authorization-server  (RFC 8414)
   Returns OUR proxy endpoints (not Entra's) so Claude routes auth through
   /authorize and /token, which strip the Azure-specific 'resource' parameter
   before forwarding to Entra. Exposing Entra's endpoints here lets Claude
   detect and bypass the proxy → AADSTS9010010.

2. /.well-known/oauth-protected-resource  (RFC 9728)
   Required by the MCP spec — tells clients which authorization server
   protects this resource.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

import config

router = APIRouter(tags=["discovery"])


def _server_uri() -> str:
    return config.BASE_URL.rstrip("/")


def _resource_uri() -> str:
    """OAuth resource identifier — the MCP endpoint URL (not api://)."""
    return f"{_server_uri()}/mcp"


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata():
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    server = _server_uri()
    return JSONResponse(
        content={
            # issuer MUST match this document's URL; if it equals Entra's URL,
            # Claude.ai validates the mismatch, rejects our proxy, and hits
            # Entra directly — sending the raw 'resource' param → AADSTS9010010.
            "issuer": server,
            "authorization_endpoint": f"{server}/authorize",
            "token_endpoint": f"{server}/token",
            "registration_endpoint": f"{server}/register",
            # api://xxx/access_as_user is intentionally omitted here;
            # the /authorize proxy injects it before forwarding to Entra.
            "scopes_supported": ["openid", "profile", "email", "offline_access"],
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": [
                "authorization_code", "client_credentials", "refresh_token"
            ],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post", "client_secret_basic", "none"
            ],
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    """Protected Resource Metadata (RFC 9728 §3)."""
    server = _server_uri()
    return JSONResponse(
        content={
            "resource": _resource_uri(),
            # Point to our server so the issuer in oauth-authorization-server matches.
            # Pointing to Entra here causes Claude.ai to validate our AS issuer
            # against Entra's — they differ → Claude bypasses our proxy.
            "authorization_servers": [server],
            "scopes_supported": ["openid", "profile", "email", "offline_access"],
            "bearer_methods_supported": ["header"],
            "resource_signing_alg_values_supported": ["RS256"],
            "resource_name": config.SERVICE_NAME,
            "resource_documentation": f"{server}/docs",
        },
        headers={"Cache-Control": "max-age=3600"},
    )
