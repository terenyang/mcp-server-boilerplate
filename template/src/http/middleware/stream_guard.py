"""Stream concurrency controller for MCP streamable-HTTP transport."""
import asyncio
import contextlib
import time

from fastapi.responses import JSONResponse

import config

MAX_CONCURRENT_STREAMS = getattr(config, "MAX_CONCURRENT_STREAMS", 20)
QUEUE_WAIT_TIMEOUT = getattr(config, "QUEUE_WAIT_TIMEOUT", 5)
HARD_STREAM_TIMEOUT = getattr(config, "HARD_STREAM_TIMEOUT", 300)
IDLE_STREAM_TIMEOUT = getattr(config, "IDLE_STREAM_TIMEOUT", 60)


class StreamConcurrencyController:
    """ASGI middleware that caps concurrent MCP streams."""

    def __init__(
        self,
        app,
        max_concurrent: int,
        queue_timeout: float,
        hard_timeout: float,
        idle_timeout: float,
    ):
        self._app = app
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue_timeout = queue_timeout
        self._hard_timeout = hard_timeout
        self._idle_timeout = idle_timeout
        self._active_streams = 0
        self._lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self._app(scope, receive, send)

        acquired = False
        try:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(), timeout=self._queue_timeout
                )
                acquired = True
                async with self._lock:
                    self._active_streams += 1
            except asyncio.TimeoutError:
                response = JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(int(self._queue_timeout))},
                    content={
                        "error": "mcp_server_busy",
                        "message": "Too many concurrent streaming requests, please retry later",
                    },
                )
                await response(scope, receive, send)
                return

            last_sent = time.monotonic()
            response_started = False

            async def send_wrapper(message):
                nonlocal last_sent, response_started
                if message["type"] == "http.response.start":
                    response_started = True
                if message["type"] == "http.response.body":
                    if message.get("body") or message.get("more_body"):
                        last_sent = time.monotonic()
                await send(message)

            async def app_runner():
                await self._app(scope, receive, send_wrapper)

            async def idle_watchdog(task: asyncio.Task):
                while not task.done():
                    await asyncio.sleep(1)
                    if time.monotonic() - last_sent > self._idle_timeout:
                        task.cancel()
                        break

            async def hard_watchdog(task: asyncio.Task):
                await asyncio.sleep(self._hard_timeout)
                if not task.done():
                    task.cancel()

            app_task = asyncio.create_task(app_runner())
            idle_task = asyncio.create_task(idle_watchdog(app_task))
            hard_task = asyncio.create_task(hard_watchdog(app_task))

            try:
                await app_task
            except asyncio.CancelledError:
                if not response_started:
                    response = JSONResponse(
                        status_code=503,
                        content={
                            "error": "mcp_stream_timeout",
                            "message": "Streaming request exceeded server timeouts",
                        },
                    )
                    await response(scope, receive, send)
                return
            finally:
                idle_task.cancel()
                hard_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await idle_task
                with contextlib.suppress(asyncio.CancelledError):
                    await hard_task
        finally:
            if acquired:
                async with self._lock:
                    self._active_streams -= 1
                self._semaphore.release()
