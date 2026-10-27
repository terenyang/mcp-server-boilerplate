## 1. Baseline and spike

- [x] 1.1 On the current 1.26 build, run the app in `api_key` mode and save the `initialize` and `tools/list` responses to `openspec/changes/upgrade-mcp-sdk-v2/baseline/`; verify both JSON files exist and list `whoami`, `ping`, `server_profile`
- [x] 1.2 In `template/pyproject.toml` change `mcp[cli]==1.26.0` to `mcp[cli]==2.3.0`, run `uv lock && uv sync`; verify `uv.lock` contains `mcp 2.3.0` and `mcp-types 2.3.0`, and that FastAPI, Starlette and pydantic versions are unchanged
- [x] 1.3 In a scratch script (not committed), confirm against the installed package: `mcp.server.mcpserver.MCPServer` and `mcp.server.mcpserver.exceptions.ToolError` import, `mcp.server.fastmcp` import fails, `streamable_http_app` accepts `streamable_http_path`, `stateless_http` and `transport_security`, and `@mcp.tool()` still returns a callable function; record any difference from design.md and update it before continuing

## 2. Server and transport

- [x] 2.1 In `template/src/server.py` replace `FastMCP` with `MCPServer(name=config.SERVICE_NAME)` and define `MCP_TRANSPORT_SECURITY` (protection disabled, hosts and origins `"*"`); verify `python -c "import src.server"` succeeds
- [x] 2.2 In `template/src/http/mcp_mount.py` import `MCP_TRANSPORT_SECURITY` and call `mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, transport_security=MCP_TRANSPORT_SECURITY)`; update the module docstring; verify the app starts and `GET /health` returns 200

## 3. tool_guard and ping

- [x] 3.1 In `template/src/deps.py` make `tool_guard` re-raise `ToolError`, log other exceptions with `logger.warning(..., exc_info=True)` and raise `ToolError(str(exc)) from exc`, with `get_auth()` and the dependency loop inside the `try`; update the module docstring and the "FastMCP" wording; verify with a unit test that a `PermissionError` from a dependency surfaces as `ToolError` with the same text and that an existing `ToolError` is not re-wrapped
- [x] 3.2 Add `@tool_guard(depends_on=[check_entra_groups])` to `ping` in `template/src/server.py`; verify the existing `test_ping_includes_message` still passes, adjusting its auth setup if needed
- [x] 3.3 Add `claims: dict` (default empty) to `AuthContext` in `template/src/auth_context.py`; make `authenticate()` in `template/src/http/middleware/jwt.py` return the validated payload as a fourth value; make `template/src/http/middleware/auth.py` store it on the `AuthContext`; verify with tests that a Bearer caller (with `authenticate` patched) whose `groups` claim is allowed, not allowed, or absent gets the result, "not authorized" error, or "No Entra groups found" error respectively

## 4. Wire-level tests

- [x] 4.1 Add a test helper under `template/tests/` that builds the FastAPI app with its lifespan running and an ASGI client authenticated by API key; verify a trivial `GET /health` test passes through it
- [x] 4.2 Add tests for `POST /mcp` and `POST /mcp/` `initialize` (both 200, no redirect), a request with `Host: example.devtunnels.ms` (not 421/403), and `tools/call` without a prior initialize; verify they pass
- [x] 4.3 Add a `tools/list` test asserting `whoami`, `ping` and `server_profile` with input schemas, and compare against the baseline from 1.1 allowing only the known wire differences; verify it passes
- [x] 4.4 Add restricted-mode tests (`ALLOWED_ENTRA_GROUPS` set, API-key caller): `whoami` and `ping` return `isError` true with text containing "No Entra groups found in token"; a bad `ping` argument type returns a validation error text; verify they pass and that a warning with traceback is logged for the guarded failure

## 5. Comments and docs

- [x] 5.1 Replace FastMCP wording with MCPServer in comments and docstrings of `template/src/http/app.py`, `template/src/auth_context.py` and `template/src/http/middleware/auth.py`; verify `grep -ri fastmcp template/src` finds nothing
- [x] 5.2 Update `README.md` and `docs/` mentions of FastMCP to "MCP Python SDK 2.x (`MCPServer`)", and add a note that `tool_guard` converts exceptions to `ToolError` and that `mcp.server.fastmcp` no longer exists; verify `grep -ri fastmcp README.md docs/*.md` finds only intentional references

## 6. Acceptance

- [x] 6.1 Run `uv sync` and the full test suite in `template/`; verify all tests pass
- [x] 6.2 Start the app locally, press Ctrl+C, and verify startup and shutdown raise no exceptions in the log
- [x] 6.3 Build the Docker image and run a `tools/list` against the container; verify the same three tools are returned
