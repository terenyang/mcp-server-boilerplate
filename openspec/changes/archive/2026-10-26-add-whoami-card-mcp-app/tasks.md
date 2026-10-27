## 1. Spike

- [x] 1.1 In a scratch script (not committed) confirm against the installed mcp 2.3.0: an `Apps()` populated before `MCPServer(extensions=[apps])` exposes the tool and resource over the real ASGI app, while one populated after construction is silently ignored; `ResourcePermissions` accepts `clipboard_write={}`; a tool returning `CallToolResult` through `tool_guard` yields text plus structured content with no output schema; record any difference from design.md and update it before continuing

## 2. Configuration and shared identity

- [x] 2.1 Add `ENABLE_MCP_APPS` to `template/config.py` (default true; `false`, `0`, `no` in any case disable) and to `template/.env.example`; verify with a unit test that the default is on and each disabling value turns it off
- [x] 2.2 Create `template/src/identity.py` with `identity_info()` returning the dict `whoami` builds today, and make `whoami` use it; verify the existing `whoami` tests still pass

## 3. Bridge and app package

- [x] 3.1 Create `template/src/apps/app_bridge.js` exposing `McpApp` (`request`, `notify`, `callTool`, `sendMessage`, `openLink`, `onNotification`, `onRequest`, `onTeardown`, `applyHostContext`, `reportSize`, `connect`) per design D4; verify with a pytest that the file is served inlined by `load_app_html` in the next task and contains the `ui/initialize` handshake
- [x] 3.2 Create `template/src/apps/loader.py` with `load_app_html(name)` that inlines the bridge at the `/*__APP_BRIDGE__*/` placeholder and raises if the placeholder is missing, `template/src/apps/registry.py` holding the single shared `Apps()`, and `template/src/apps/__init__.py` that imports the app modules and exports `apps`, `APP_CALLABLE_META` and `load_app_html`; verify with unit tests for replacement, the missing-placeholder error, and that the package exports the shared registry
- [x] 3.3 Create `template/src/apps/whoami_card.py` registering on the shared registry the `ui://` resource (`prefers_border=True`, clipboard permission) and the `whoami_card` tool (`@apps.tool` outside `@tool_guard(depends_on=[check_entra_groups])`) returning `CallToolResult` with text and structured identity; verify with unit tests for the API-key and Bearer text and structured content
- [x] 3.4 Create `template/src/apps/whoami_card.html` (fallback theme variables with dark mode, 360 px layout, identity display, Ping button, Send to chat with array retry and copyable fallback, size reporting, teardown handling, `textContent` only); verify with a pytest that the HTML has no `http:`/`https:` script or stylesheet sources and no `@import`

## 4. Server wiring

- [x] 4.1 In `template/src/server.py` pass `extensions=[apps] if config.ENABLE_MCP_APPS else []` to `MCPServer` and add `meta=APP_CALLABLE_META` to `ping`; verify `python -c "import src.server"` succeeds and `tools/list` shows `whoami_card` and `ping` metadata
- [x] 4.2 Update `template/tests/test_mcp_wire.py`: baseline test becomes "all baseline tools present, differing only by `ping` `_meta` and the added `whoami_card`"; add wire tests for the `ui://` resource read (MIME type, no placeholder), `whoami_card` calls for API-key and patched Bearer callers, restricted-mode error text, and that `whoami` and `server_profile` have no app visibility; verify they pass
- [x] 4.3 Add a subprocess test that starts the app with `ENABLE_MCP_APPS=false` and asserts `tools/list` equals the pre-upgrade baseline fixture exactly and `resources/list` has no `ui://` entry; verify it passes and that the same test fails when apps are enabled

## 5. Mock host

- [x] 5.1 Create `template/scripts/mcp_app_host/serve.py` (127.0.0.1 only, API key from an environment variable, real-mode JSON-RPC proxy that handles JSON and SSE replies) and `host.html` generalized per design D7 (resource discovery, scenarios `bearer`, `apikey`, `denied`, `theme`, `width`, `msgArray`, `__hostLog`, chat message capture, visibility check, teardown button); verify real mode renders the card against a locally running server
- [x] 5.2 Using Playwright against the mock host, verify: handshake and render for each scenario; Ping returns text and shows an error under `denied`; Send to chat sends nothing until clicked, succeeds, and with `msgArray=1` retries as an array; teardown is answered and the page stops timers; dark theme applies; the card works at 360 px; the reported height shrinks when content shrinks; record the results in the change notes

## 6. Documentation

- [x] 6.1 Update `README.md`: SDK wording is already updated, add an MCP Apps section (directory structure, the registration-order constraint, `APP_CALLABLE_META` and the opt-in rule, `ENABLE_MCP_APPS`, the mock host usage, "restart after editing HTML", and the pattern for steering the model without implementing it); verify each item appears
- [x] 6.2 Update the README "Add Your Own Tool" section to mention `meta=APP_CALLABLE_META` for tools an app calls, and add `scripts/` and `src/apps/` to any directory listing in the docs; verify with a search

## 7. Acceptance

- [x] 7.1 Run `uv sync` and the full test suite in `template/`; verify everything passes
- [x] 7.2 Build the Docker image and verify `resources/read` of the `ui://` resource inside the container returns the complete HTML including the inlined bridge, then remove the image
- [x] 7.3 Record in the change notes which real-client checks are still manual (Claude Desktop, Claude web, Copilot Studio text fallback, Postman) so they are not mistaken for done
