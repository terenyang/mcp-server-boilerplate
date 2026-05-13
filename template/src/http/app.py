"""FastAPI application — routers, middleware, lifespan."""
import contextlib
import logging
from datetime import datetime, timezone

import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.server import mcp
from src.http.middleware.auth import AuthenticationMiddleware
from src.http.middleware.stream_guard import (
    MAX_CONCURRENT_STREAMS,
    QUEUE_WAIT_TIMEOUT,
    HARD_STREAM_TIMEOUT,
    IDLE_STREAM_TIMEOUT,
)
from src.http.mcp_mount import mount_mcp, MCPPathMiddleware
from src.http.well_known import router as well_known_router
from src.http.oauth_proxy import router as oauth_proxy_router
import config

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """FastMCP streamable HTTP requires session_manager.run() even in stateless mode."""
    logger.info("Starting %s", config.SERVICE_NAME)
    async with mcp.session_manager.run():
        yield
    logger.info("%s shutdown complete", config.SERVICE_NAME)


app = FastAPI(
    title=config.SERVICE_NAME,
    description="MCP Server boilerplate — OAuth2 + API key auth",
    version=config.SERVICE_VERSION,
    lifespan=lifespan,
)

# Raw ASGI middlewares preserve contextvars through streaming responses.
# add_middleware inserts at index 0 — last call becomes the outermost wrapper.
# Order: AuthenticationMiddleware (outer) → MCPPathMiddleware → router
app.add_middleware(MCPPathMiddleware)       # inner: path rewriting
app.add_middleware(AuthenticationMiddleware)  # outer: auth checking (runs first)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(well_known_router)
app.include_router(oauth_proxy_router)

_guarded_mcp = mount_mcp(app)


@app.get("/")
async def root():
    return JSONResponse({
        "service": config.SERVICE_NAME,
        "owner": config.SERVICE_OWNER,
        "version": config.SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health",
        "mcp": "/mcp",
    })


@app.get("/health")
async def health():
    process = psutil.Process()
    mem = process.memory_info()
    sys_mem = psutil.virtual_memory()
    return JSONResponse({
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": config.SERVICE_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "mcp": {
                "active_streams": _guarded_mcp._active_streams,
                "max_streams": MAX_CONCURRENT_STREAMS,
                "queue_wait_timeout_s": QUEUE_WAIT_TIMEOUT,
                "hard_timeout_s": HARD_STREAM_TIMEOUT,
                "idle_timeout_s": IDLE_STREAM_TIMEOUT,
            },
            "memory": {
                "process_rss_mb": round(mem.rss / (1024 * 1024), 2),
                "system_used_pct": sys_mem.percent,
            },
        },
    })
