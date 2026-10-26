"""StreamConcurrencyController driven directly as an ASGI callable.

Timeouts are a few seconds at most; the idle watchdog polls once per second,
so a request is cancelled at the first poll after its idle period expires.
"""
import asyncio
import json

import pytest

from src.http.middleware.stream_guard import StreamConcurrencyController

HTTP_START = {"type": "http.response.start", "status": 200, "headers": []}
FINAL_EMPTY = {"type": "http.response.body", "body": b"", "more_body": False}


def make_guard(app, *, max_concurrent=5, queue=0.2, hard=30.0, idle=0.5):
    return StreamConcurrencyController(
        app,
        max_concurrent=max_concurrent,
        queue_timeout=queue,
        hard_timeout=hard,
        idle_timeout=idle,
    )


async def call(guard, method="POST"):
    """Run one request through the guard and return the messages it sent."""
    messages = []

    async def receive():
        await asyncio.sleep(3600)

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "method": method, "path": "/mcp/", "headers": []}
    await asyncio.wait_for(guard(scope, receive, send), timeout=15)
    return messages


def status_of(messages):
    return messages[0]["status"]


def json_body(messages):
    return json.loads(b"".join(m.get("body", b"") for m in messages[1:]))


async def quick_app(scope, receive, send):
    await send(HTTP_START)
    await send({"type": "http.response.body", "body": b"ok", "more_body": False})


# --- concurrency cap --------------------------------------------------------

async def test_cap_exceeded_returns_429_and_slot_is_released():
    release = asyncio.Event()

    async def blocking_app(scope, receive, send):
        await release.wait()
        await quick_app(scope, receive, send)

    guard = make_guard(blocking_app, max_concurrent=1, queue=0.2)
    first = asyncio.create_task(call(guard))
    while guard._active_streams < 1:
        await asyncio.sleep(0.01)

    rejected = await call(guard)

    assert status_of(rejected) == 429
    header_names = {k.lower() for k, _ in rejected[0]["headers"]}
    assert b"retry-after" in header_names

    release.set()
    assert status_of(await first) == 200
    assert guard._active_streams == 0

    assert status_of(await call(guard)) == 200
    assert guard._active_streams == 0


# --- idle timeout -----------------------------------------------------------

async def test_idle_post_before_any_response_gets_503():
    async def silent_app(scope, receive, send):
        await asyncio.sleep(30)

    guard = make_guard(silent_app, idle=0.5)

    messages = await call(guard, "POST")

    assert status_of(messages) == 503
    assert json_body(messages)["error"] == "mcp_stream_timeout"
    assert guard._active_streams == 0


async def test_idle_get_stream_stays_open_past_idle_timeout():
    async def sse_app(scope, receive, send):
        await send(HTTP_START)
        await asyncio.sleep(2.5)  # silent for 5x the idle timeout
        await send({"type": "http.response.body", "body": b"data: late\n\n", "more_body": False})

    guard = make_guard(sse_app, idle=0.5)

    messages = await call(guard, "GET")

    assert messages[-1]["body"] == b"data: late\n\n"
    assert all(m.get("status") != 503 for m in messages)
    assert guard._active_streams == 0


async def test_response_start_counts_as_activity():
    async def slow_app(scope, receive, send):
        await asyncio.sleep(1.2)
        await send(HTTP_START)
        await asyncio.sleep(1.2)
        await send({"type": "http.response.body", "body": b"done", "more_body": False})

    guard = make_guard(slow_app, idle=1.5)

    messages = await call(guard, "POST")

    assert status_of(messages) == 200
    assert messages[-1]["body"] == b"done"


# --- hard timeout and clean termination -------------------------------------

async def test_get_stream_is_closed_at_hard_timeout_with_final_body():
    async def endless_sse(scope, receive, send):
        await send(HTTP_START)
        await asyncio.sleep(30)

    guard = make_guard(endless_sse, hard=1.0, idle=0.5)

    messages = await call(guard, "GET")

    assert messages[-1] == FINAL_EMPTY
    assert guard._active_streams == 0


async def test_cancelled_mid_stream_response_is_finished():
    async def stalls_after_chunk(scope, receive, send):
        await send(HTTP_START)
        await send({"type": "http.response.body", "body": b"part", "more_body": True})
        await asyncio.sleep(30)

    guard = make_guard(stalls_after_chunk, idle=0.5)

    messages = await call(guard, "POST")

    assert messages[1]["body"] == b"part"
    assert messages[-1] == FINAL_EMPTY
    assert guard._active_streams == 0


async def test_completed_response_gets_no_extra_final_body():
    guard = make_guard(quick_app)

    messages = await call(guard)

    assert [m["type"] for m in messages] == ["http.response.start", "http.response.body"]
    assert guard._active_streams == 0


async def test_body_without_more_body_key_counts_as_complete():
    # Starlette's Response sends the final body without a more_body key; the
    # ASGI default is False, so the guard must not append another message.
    async def starlette_style_app(scope, receive, send):
        await send(HTTP_START)
        await send({"type": "http.response.body", "body": b"ok"})

    guard = make_guard(starlette_style_app)

    messages = await call(guard)

    assert len(messages) == 2
