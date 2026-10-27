## Context

See proposal.md for motivation. Paths are under `template/`.

Starting point (after `upgrade-mcp-sdk-v2` and `sync-oauth-stream-fixes`): `src/server.py` builds `MCPServer(name=...)` and defines `whoami`, `ping`, `server_profile`; tools are wrapped by `tool_guard` from `src/deps.py`; the app runs stateless over streamable HTTP. There are 42 tests, including a wire test that compares `tools/list` with an exact pre-upgrade baseline.

Facts about mcp 2.3.0 that this design relies on come from the nextrace notes, except those marked verified:
- Verified: `mcp.server.apps` exports `Apps`, `ResourcePermissions`, `ResourceCsp`, `client_supports_apps`; `Apps.tool(*, resource_uri, visibility=None, meta=None, **tool_kwargs)` and `Apps.add_html_resource(uri, html, *, name, title, description, csp, permissions, domain, prefers_border)` exist; `CallToolResult` (from `mcp_types`) has `content`, `structured_content`, `is_error`, `result_type`; `MCPServer.__init__` accepts `extensions`.
- Verified by the spike: an `Apps()` populated before `MCPServer(extensions=[apps])` exposes its tool and resource, while one populated after construction is silently ignored (`tools=[]`, `resources=[]`); `ResourcePermissions` accepts both `clipboard_write=` and `clipboardWrite=` and serializes to `clipboardWrite`; a `CallToolResult` return passes through `tool_guard` unchanged with no output schema; the app tool's `_meta` carries both `ui/resourceUri` and `ui.resourceUri`.
- Not independently verified: `client_supports_apps` being always false in stateless mode. The design does not depend on it, because the tool always returns text plus structured content.
- Verified against the nextrace repo: `src/nextrace/apps/` and `scripts/mcp_app_host/` are the reference implementations, and `scripts/` is not ignored in this template.

## Goals / Non-Goals

**Goals:**
- A minimal, correct, testable app example that derived services copy.
- All host-protocol behavior implemented once in a shared bridge.
- Apps strictly optional: `ENABLE_MCP_APPS=false` yields the pre-app server.

**Non-Goals:**
- Steering the model toward the app (`instructions`, "DEFAULT way to" wording, server-side enforcement). The README describes the pattern; the template does not implement it.
- A UI framework, bundler or npm tooling.
- A general-purpose host; the mock host exists to test apps.

## Decisions

**D1. Apps live in their own package and `server.py` only imports them.**
`Apps()` must hold all tools and resources before `MCPServer(...)` is constructed. The single shared `Apps()` lives in `src/apps/registry.py` so no app depends on another app's file; app modules register on it, `src/apps/__init__.py` imports them (populating the registry) and exports `apps`, `APP_CALLABLE_META` and `load_app_html`; `server.py` imports from the package and passes `extensions=[apps] if config.ENABLE_MCP_APPS else []`.
Alternative: define app tools in `server.py` above the constructor. Rejected: it hides the ordering constraint and clutters the file derived services edit most.

**D2. Shared identity data in `src/identity.py`.**
`whoami` and `whoami_card` need the same dict. `server.py` imports `apps`, so `whoami_card.py` cannot import `server.py` without a cycle. A small `identity_info()` module that depends only on `auth_context` removes the cycle and the duplication.
Alternative: put it in `auth_context.py`. Rejected: that module is only the context variable and dataclass.

**D3. Tool result carries text and structured content, never chosen by client capability.**
Stateless mode forgets `initialize`, so `client_supports_apps` cannot be trusted. The result always has text (what the model and UI-less clients read) plus structured content (what the UI renders). The return annotation is `CallToolResult`. The decorator order is `@apps.tool(...)` outside and `@tool_guard(...)` inside, as with `@mcp.tool()`.

**D4. Shared bridge inlined by Python.**
`src/apps/app_bridge.js` exposes one global (`McpApp`) with `request`, `notify`, `callTool`, `sendMessage` (object first, array retry), `openLink` (new-tab fallback), `onNotification`, `onRequest`, `onTeardown`, `applyHostContext`, `reportSize` and `connect({appInfo, onFail})`. `load_app_html(name)` reads the HTML and replaces the `/*__APP_BRIDGE__*/` placeholder with the JS, once at import. Inlining keeps the resource self-contained, which the default CSP (`default-src 'none'`, inline allowed, no network) requires.
Protocol details kept from nextrace: version `2026-01-26`; nothing is sent by the host before `ui/notifications/initialized`; size is measured on `document.body` with a `ResizeObserver`, never `documentElement.scrollHeight`; tool results are unwrapped as `isError` then `structuredContent` (taking `.result` when it is the only key) then JSON text; DOM is built with `textContent` and `replaceChildren(...children.filter(Boolean))`.
Alternative: copy the bridge into each HTML file. Rejected: templates grow more apps, and bridge fixes would have to be repeated.

**D5. Only `ping` is app-callable.**
`APP_CALLABLE_META = {"ui": {"visibility": ["model", "app"]}}` when apps are enabled, else `None`, applied to `ping` through `@mcp.tool(meta=APP_CALLABLE_META)`. The card needs only `ping`; widening the app-callable surface has a security cost (app calls run with the user's token). The README tells authors to opt other tools in explicitly.

**D6. Send to chat uses `ui/message` on click, with an array retry.**
`ui/update-model-context` is not forwarded to the model by Claude Desktop, so it is not relied on. Send the single-object content first; on error retry once with `[ {type, text} ]`; if both fail, show the error and a read-only field with the text selected. Clipboard use is also guarded for the same reason: the sandbox may block it.

**D7. Mock host is generalized, not copied.**
Real mode discovers the app tool and resource URI from `tools/list` (`_meta.ui.resourceUri`) instead of hardcoding names, and gets the HTML from `resources/read`. Mock mode serves the local HTML file and implements `tools/list`, `resources/read` and `tools/call` for `whoami_card` and `ping` with scenarios `bearer`, `apikey`, `denied`. Kept: `theme`, `width`, `msgArray`, `__hostLog`, the visibility check and the teardown button. `serve.py` reads the API key from an environment variable and binds to 127.0.0.1 only.

**D8. Tests.**
- Wire (in-process, shared client): `tools/list` includes `whoami_card` with `_meta.ui.resourceUri` and `ping` with app visibility; `resources/read` returns the `text/html;profile=mcp-app` document with no placeholder and no external references; `tools/call whoami_card` returns text and structured content for API-key and (patched) Bearer callers; restricted mode returns the authorization text.
- Disabled mode runs in a subprocess with `ENABLE_MCP_APPS=false`, because extensions are fixed at construction: it asserts the tool set and metadata equal the pre-upgrade baseline fixture and that there are no `ui://` resources.
- The existing exact-baseline test becomes: baseline tools all present, differing only by `_meta` on `ping` and the added `whoami_card`.
- Unit: `load_app_html` replaces the placeholder and fails loudly if the placeholder is missing.
- Browser: use Playwright against the mock host for handshake, ping, send-to-chat (including `msgArray=1`), teardown, dark theme, 360 px width and height shrink. These run during acceptance and are not part of the default pytest run.

## Risks / Trade-offs

- [Unverified 2.3.0 behaviors (extensions at construction, permissions alias, `CallToolResult` through `tool_guard`)] -> The first task is a spike that checks each; update this design if any differs.
- [Real clients differ from the mock host] -> The mock enforces the documented rules, but the final check is Claude Desktop and Claude web; those remain a manual acceptance step.
- [HTML is read at import; `--reload` watches only `.py`] -> README states "restart after editing HTML".
- [`ENABLE_MCP_APPS` disabled test needs a subprocess and is slower] -> One short test; acceptable.
- [Playwright runs are not in CI] -> Acceptable for a template; the pytest wire tests and the HTML-content checks run in CI.
- [Hosts may interpret a missing `_meta.ui` on other tools differently] -> The spec leaves it undefined; by design only the tools the app needs are marked.

## Migration Plan

Single branch, several commits. Existing deployments are unaffected unless they take the new template version; they can set `ENABLE_MCP_APPS=false` to keep the previous tool list. Rollback is a revert.
