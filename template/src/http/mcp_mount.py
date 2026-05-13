"""Mount FastMCP streamable-HTTP app onto the FastAPI instance at /mcp."""
from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from src.server import mcp
from src.http.middleware.stream_guard import (
    StreamConcurrencyController,
    MAX_CONCURRENT_STREAMS,
    QUEUE_WAIT_TIMEOUT,
    HARD_STREAM_TIMEOUT,
    IDLE_STREAM_TIMEOUT,
)


class MCPPathMiddleware:
    """Rewrite bare /mcp to /mcp/ to prevent Starlette's 307 redirect.

    Copilot Studio and Claude Desktop don't follow POST 307 redirects,
    so this middleware prevents the redirect from ever being issued.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = {**scope, "path": "/mcp/"}
        await self.app(scope, receive, send)


def mount_mcp(app: FastAPI) -> StreamConcurrencyController:
    """Wrap the MCP ASGI app with concurrency control and mount at /mcp."""
    streamable_app = mcp.streamable_http_app()
    guarded = StreamConcurrencyController(
        streamable_app,
        max_concurrent=MAX_CONCURRENT_STREAMS,
        queue_timeout=QUEUE_WAIT_TIMEOUT,
        hard_timeout=HARD_STREAM_TIMEOUT,
        idle_timeout=IDLE_STREAM_TIMEOUT,
    )
    app.mount("/mcp", guarded)
    return guarded
