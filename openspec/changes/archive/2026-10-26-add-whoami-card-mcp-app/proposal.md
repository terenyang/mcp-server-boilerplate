## Why

Services built from the template cannot yet show interactive UI in clients that support MCP Apps (Claude Desktop, Claude web). The nextrace service proved the pattern and also hit a long list of pitfalls (registration order, stateless mode, iframe sizing, chat messaging). The template needs a small, working example so derived services start from a correct pattern instead of rediscovering those pitfalls.

## What Changes

- Add an `apps` package under `template/src/apps/` with one example app, `whoami_card`: a tool plus a `ui://` resource that renders the signed-in identity, lets the user call `ping` through the host, and lets the user send a message to the chat.
- Add a shared browser-side bridge (`app_bridge.js`) that implements the host handshake, tool calls, theming, size reporting and teardown; the Python side inlines it into each HTML file so no external resource is needed.
- Register the app on `MCPServer` through `extensions`, gated by a new `ENABLE_MCP_APPS` setting (default on). When off, the tool list and resource list equal the pre-app server.
- Mark `ping` as callable by the app (`APP_CALLABLE_META`) so hosts accept the app's `tools/call`; other tools stay model-only unless their authors opt in.
- Move the identity data shared by `whoami` and `whoami_card` into one small module so the apps package never imports `server.py`.
- Add a mock MCP Apps host under `template/scripts/mcp_app_host/` so apps can be exercised and tested without a real client.
- Update the tests that assumed exactly three tools, and add tests for the app tool, the resource, the visibility metadata, the setting, and the HTML bridge.
- Document the pattern in the README and `.env.example`.
- Out of scope: server-level `instructions` and server-side enforcement that steer the model toward the app (README mentions the pattern only), `user_role`, and `mcp_smoke.py`.

## Capabilities

### New Capabilities
- `mcp-apps`: how the service exposes MCP Apps: the example tool and its `ui://` resource, the enable/disable setting, which tools an app may call, and the text fallback for clients without UI.
- `mcp-app-dev-host`: the local mock host used to run and test apps, including its simulated host behaviors.

### Modified Capabilities

None. `mcp-http-transport` and `tool-error-reporting` keep their requirements; the tool list scenario that names exactly three tools is superseded in practice, but its text ("contains whoami, ping and server_profile") still holds.

## Impact

- Code: new `template/src/apps/` (package, bridge, `whoami_card.py`, `whoami_card.html`), new `template/src/identity.py`, edits to `template/src/server.py` and `template/config.py`, new `template/scripts/mcp_app_host/`, edits to `template/tests/`, `template/.env.example` and `README.md`.
- Wire behavior: `tools/list` gains `whoami_card`; `ping` and `whoami_card` carry `_meta.ui`; `resources/list` gains one `ui://` resource (all only when `ENABLE_MCP_APPS` is on).
- Dependencies: none new (`mcp.server.apps` and `mcp_types` ship with mcp 2.3.0).
- Packaging: the Dockerfile already copies `src/`; the HTML and JS files travel with it.
