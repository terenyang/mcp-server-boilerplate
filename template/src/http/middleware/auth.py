"""Authentication middleware — MCP authorization flow (resource server role).

Implemented as a raw ASGI middleware (not BaseHTTPMiddleware) so that
contextvars propagate correctly through FastMCP's streaming responses.
BaseHTTPMiddleware wraps responses in a new task, which can break context
propagation for the streaming MCP transport.

Flow:
  1. No token present       → 401 + WWW-Authenticate (resource_metadata URL)
  2. Bearer token present   → validate JWT; 401/403 if invalid
  3. x-api-key fallback     → validate API key

Sets auth context before calling the next ASGI app so MCP tools can read it
via src.auth_context.get_auth() without any explicit argument passing.
"""
import json
import logging

from fastapi import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from src.http.middleware.api_key import ensure_valid_api_key
from src.http.middleware.jwt import authenticate
from src.auth_context import AuthContext, set_auth
import config

logger = logging.getLogger(__name__)

EXEMPT_PREFIXES = [
    "/.well-known/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/register",
    "/authorize",
    "/token",
]

EXEMPT_EXACT = {"/", "/health"}

_RESOURCE_METADATA_URL = (
    f"{config.BASE_URL.rstrip('/')}/.well-known/oauth-protected-resource"
)


async def _send_json(send: Send, status_code: int, body: dict, extra_headers: dict | None = None) -> None:
    content = json.dumps(body).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(content)).encode()),
    ]
    if extra_headers:
        for k, v in extra_headers.items():
            headers.append((k.encode(), v.encode()))

    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": headers,
    })
    await send({
        "type": "http.response.body",
        "body": content,
        "more_body": False,
    })


class AuthenticationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path in EXEMPT_EXACT or any(path.startswith(p) for p in EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))

        # ── Bearer token (Azure AD / Entra) ──────────────────────────────────
        auth_header = headers.get(b"authorization", b"").decode("latin-1")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                user_oid, user_name, user_upn = await authenticate(token)
                set_auth(AuthContext(
                    auth_type="bearer",
                    user_oid=user_oid,
                    user_name=user_name,
                    user_upn=user_upn,
                ))
                logger.info("Bearer auth: %s (%s)", user_oid, user_name)
                await self.app(scope, receive, send)
                return
            except HTTPException as exc:
                code = 403 if exc.status_code == 403 else 401
                extra = {}
                if code == 401:
                    extra["WWW-Authenticate"] = (
                        f'Bearer resource_metadata="{_RESOURCE_METADATA_URL}"'
                    )
                await _send_json(send, code, {"detail": exc.detail}, extra)
                return
            except Exception:
                await _send_json(
                    send, 401, {"detail": "Invalid or expired token"},
                    {"WWW-Authenticate": f'Bearer resource_metadata="{_RESOURCE_METADATA_URL}"'},
                )
                return

        # ── x-api-key ─────────────────────────────────────────────────────────
        api_key = headers.get(b"x-api-key", b"").decode("latin-1")
        if not api_key:
            await _send_json(
                send, 401, {"detail": "Authorization required"},
                {"WWW-Authenticate": f'Bearer resource_metadata="{_RESOURCE_METADATA_URL}"'},
            )
            return

        try:
            ensure_valid_api_key(api_key)
        except HTTPException as exc:
            await _send_json(send, exc.status_code, {"detail": exc.detail})
            return
        except Exception:
            await _send_json(send, 403, {"detail": "Invalid API key"})
            return

        set_auth(AuthContext(auth_type="api_key"))
        logger.info("API key auth accepted")
        await self.app(scope, receive, send)
