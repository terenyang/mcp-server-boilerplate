## Context

See proposal.md for motivation. All paths below are under `template/`.

Current shape: `src/server.py` builds `FastMCP(..., stateless_http=True, streamable_http_path="/", transport_security=...)` and defines tools with `@mcp.tool()`. `src/http/mcp_mount.py` calls `mcp.streamable_http_app()` and mounts it at `/mcp`, behind `MCPPathMiddleware` (`/mcp` to `/mcp/`) and `StreamConcurrencyController`. `tool_guard` in `src/deps.py` runs dependencies and re-raises whatever they raise. `tests/test_tools.py` imports tool functions directly and has no wire-level coverage.

The facts about mcp 2.3.0 used here come from the nextrace upgrade notes (`TEMPLATE_UPGRADE_HANDOFF.md`), not from this repo. The first task therefore verifies them against the installed package before the rest is built on them.

## Goals / Non-Goals

**Goals:**
- Template runs on `mcp 2.3.0` with `MCPServer`, with no behavior regression visible to clients other than the listed wire differences.
- Authorization and tool failure messages stay readable to clients.
- A wire-level test suite that makes later changes (OAuth fixes, MCP Apps) safe.

**Non-Goals:**
- OAuth proxy and stream_guard changes, MCP Apps, `APP_CALLABLE_META`, dev tools (other changes).
- Guarding `server_profile`; it stays unguarded and unchanged.
- Restoring `serverInfo.version` or `capabilities.experimental`.

## Decisions

**D1. Transport settings move to `streamable_http_app()`.**
`MCPServer(name=...)` takes no transport arguments in 2.x. `mount_mcp` passes `streamable_http_path="/"`, `stateless_http=True` and `transport_security=MCP_TRANSPORT_SECURITY`. `MCP_TRANSPORT_SECURITY` is defined in `server.py` so the policy sits next to the server definition.
Alternative: build the settings inside `mcp_mount.py`. Rejected because `server.py` is where later changes (Apps) already touch server construction, and one definition site is easier to find.

**D2. Always pass `TransportSecuritySettings` explicitly, with protection disabled.**
Omitting it makes 2.x auto-enable DNS rebinding protection limited to localhost, which breaks tunnels and public domains. Disabling it keeps 1.x behavior; the service already authenticates every non-exempt request.
Alternative: allow-list hosts from `config.BASE_URL`. Rejected for the template because deployments commonly sit behind several hostnames; derived services can tighten it.

**D3. `tool_guard` converts all exceptions to `ToolError`.**
2.x forwards only `ToolError` text. The wrapper re-raises `ToolError` unchanged and wraps everything else as `ToolError(str(exc))` with `raise ... from exc`, after `logger.warning(..., exc_info=True)` because the SDK logs `ToolError` without a traceback. The auth lookup moves inside the `try` so a missing auth context also becomes a readable error.
Alternative: raise `ToolError` from each dependency. Rejected because it pushes SDK coupling into every dependency and leaves tool-body exceptions unconverted.
Trade-off: converting every exception can expose internal exception text to clients. Acceptable for this template because the callers are authenticated; the README notes that tool authors should raise deliberately worded errors.

**D4. `ping` is guarded with `check_entra_groups`.**
Keeps restricted mode uniform across built-in tools and makes the "ping returns the permission message" check meaningful. Cost: `ping` is no longer usable as an unauthenticated-by-group connectivity probe in restricted mode; `/health` already serves that purpose.

**D5. Wire tests use the real ASGI app.**
Tests build the FastAPI app, drive it with an ASGI HTTP client, and send JSON-RPC to `/mcp` and `/mcp/`. They cover the behaviors in the specs. The lifespan (which starts the session manager) must be run in the test client. Existing direct-call tests stay and must still pass, which also verifies that `@mcp.tool()` still returns a callable function under 2.x.

**D6. Regression baseline.**
Before changing dependencies, record `initialize` and `tools/list` output from the 1.26 build into the change directory (`baseline/`). After the upgrade, compare. Expected diffs are only those in A6 of the handoff.

**D7. Token claims are carried on `AuthContext` (scope added during apply).**
`check_entra_groups` reads `auth.claims`, but `AuthContext` had no such field and `jwt.authenticate()` discarded the payload, so restricted mode raised `AttributeError` for every caller before this change (the SDK 1.x error text hid it). `AuthContext` gains `claims: dict` (default empty); `authenticate()` returns the validated payload as a fourth value; the auth middleware stores it. API-key callers keep an empty `claims`, so restricted mode reports "No Entra groups found in token" for them.
Alternative: only default `claims` to `{}`. Rejected: Bearer users would always be denied with a misleading message.
Alternative: separate change. Rejected by the user in favour of fixing it here, since the specs for error reporting cannot hold without it.

## Risks / Trade-offs

- [2.3.0 behavior differs from the handoff notes] -> Task 1 is a spike that runs the checks against the installed package; if anything differs, update this design before continuing.
- [Existing direct-call tests break because `@mcp.tool()` no longer returns the plain function] -> Detect in the spike; if so, export the undecorated functions or test through the ASGI client.
- [`uv lock` pulls in a different transitive set than nextrace] -> Review the lock diff; confirm FastAPI, Starlette and pydantic versions are unchanged.
- [Derived services importing `mcp.server.fastmcp` break] -> Call out in README and release notes; the import fails loudly at startup, not silently.
- [Bearer claims path cannot be exercised against real Entra in tests] -> test `check_entra_groups` with constructed `AuthContext(claims=...)` and test the middleware by patching `authenticate`; confirm with a real token during acceptance.
- [Lifespan ordering] -> `mcp.session_manager.run()` must start after `streamable_http_app()` is called; `mount_mcp` already runs first. The wire test covers it by starting the app lifespan.

## Migration Plan

1. Record baseline from the current build.
2. Bump the dependency, lock, sync; fix imports; run the spike checks.
3. Land code changes (server, mount, deps, `ping` guard) and tests together.
4. Update README and comments.
Rollback: revert the commit and re-sync the lockfile; there is no data or config migration.
