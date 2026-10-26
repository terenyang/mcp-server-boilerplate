## Why

The template pins `mcp[cli]==1.26.0` and builds on `FastMCP`. Services derived from it are one SDK generation behind the services that already run on mcp 2.x (`MCPServer`), and the MCP Apps work that follows depends on 2.x APIs. The upgrade also changes behavior that is easy to miss: tool errors lose their text unless wrapped as `ToolError`, and transport defaults reject public domains. Doing it once in the template avoids every derived service hitting these problems separately.

## What Changes

- Upgrade `mcp[cli]` from `1.26.0` to `2.3.0` and refresh `uv.lock`.
- Replace `FastMCP` with `MCPServer` in `template/src/server.py`; transport settings move off the constructor.
- Pass `streamable_http_path="/"`, `stateless_http=True` and explicit `TransportSecuritySettings` to `streamable_http_app()` in `template/src/http/mcp_mount.py`.
- `tool_guard` converts any non-`ToolError` exception into `ToolError(str(exc))` and logs the original with a traceback, so permission and validation messages reach the client.
- `ping` gets `tool_guard(depends_on=[check_entra_groups])`, so restricted mode applies to every tool consistently.
- Update FastMCP wording in comments and docstrings (`app.py`, `auth_context.py`, `middleware/auth.py`, `deps.py`, README).
- Add wire-level tests that exercise the real ASGI app, and capture a pre-upgrade `tools/list` snapshot for regression comparison.
- Out of scope: OAuth and stream_guard fixes (separate change `sync-oauth-stream-fixes`) and the MCP App example (separate change `add-whoami-card-mcp-app`).

## Capabilities

### New Capabilities
- `mcp-http-transport`: how the MCP endpoint is exposed (`/mcp` and `/mcp/` both served without redirect, non-localhost hosts accepted, stateless mode).
- `tool-error-reporting`: how tool failures, including authorization failures raised by `tool_guard`, are reported to MCP clients.

### Modified Capabilities

None. `openspec/specs/` is currently empty.

## Impact

- Code: `template/pyproject.toml`, `template/uv.lock`, `template/src/server.py`, `template/src/http/mcp_mount.py`, `template/src/deps.py`, comment-only edits in `template/src/http/app.py`, `template/src/auth_context.py`, `template/src/http/middleware/auth.py`; new tests under `template/tests/`.
- Dependencies: adds `mcp-types`, `httpx2` family and `truststore`; removes `httpx-sse` and `pydantic-settings` (per the nextrace upgrade). FastAPI, Starlette and pydantic are unchanged.
- Wire behavior: `serverInfo.version` becomes empty and `capabilities.experimental` is no longer returned; schemas are otherwise unchanged.
- Derived services: anyone importing `mcp.server.fastmcp` will get `ModuleNotFoundError` after taking this version.
