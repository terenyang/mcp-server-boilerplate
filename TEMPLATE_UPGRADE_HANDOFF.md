# MCP boilerplate template upgrade: handoff document and TODO

> Source: notes from the 2026-10 SDK upgrade and MCP Apps work on `nxt-nextrace-mcp-v2`.
> Goal: bring the boilerplate (snapshot copy in `nxt-nextrace-mcp-v2/__BACKUP__/template`) up to the same level.
> 1) upgrade to the new MCP Python SDK (2.x), 2) add a UI/App example, 3) (recommended) sync in the general fixes the template is missing.
>
> Format: each TODO item says **what to change → how to change it → how to verify it**. Code snippets come from the current nextrace HEAD (`4b289af`), and the referenced files are in that repo.

---

## 0. Background and reference sources

| Topic | nextrace commit | Main reference files |
|---|---|---|
| SDK upgrade from 1.26 to 2.3.0 | `560d178` | `pyproject.toml`, `src/server.py`, `src/http/mcp_mount.py`, `src/nextrace/deps.py` |
| OAuth / RFC 9728 / Postman compatibility | `870c8f7` | `src/http/well_known.py`, `src/http/oauth_proxy.py`, `src/http/middleware/auth.py` |
| MCP App (extraction wizard) | `8621df9`, `aa3a295` | `src/nextrace/apps/__init__.py`, `extraction_wizard.py`, `extraction_wizard.html` |
| Design decisions and pitfalls | (archived) | `openspec/changes/archive/2026-10-26-upgrade-mcp-sdk-v2/`, `.../2026-10-26-add-extraction-wizard-mcp-app/design.md` |

Where the template stands today (as of 2026-05):

```
template                         target
-------------------------------  -----------------------------------------
mcp[cli]==1.26.0 / FastMCP       mcp[cli]==2.3.0 / MCPServer
transport args in FastMCP(...)   transport args in streamable_http_app(...)
tool_guard re-raises unchanged   tool_guard converts to ToolError
OAuth: older version             + RFC 9728 path suffix, state optional, scope de-dup,
                                   token response carries resource
stream_guard: older version      + no idle timeout on SSE GET, proper response finish
no MCP Apps                      + whoami_card example (src/apps/)
```

---

## 1. Decisions (confirm before starting; defaults are recommendations)

- [ ] **D1. Sync the general fixes (section B)?** Recommended: **yes**. Otherwise services built from the template will hit the Postman and Copilot Studio problems nextrace already fixed.
- [ ] **D2. Which App example?** Recommended: **`whoami_card`** (see section C). It is small, but covers registration, the app calling a tool, sending a message to the chat, and theming.
- [ ] **D3. Factor the bridge into a shared `app_bridge.js`?** Recommended: **yes**, because a template is meant to grow more apps. When reading the HTML, Python inlines it into a `<script>` (no external references, so CSP passes).
- [ ] **D4. Should the auth middleware switch to nextrace's "only protect `/api/` and `/mcp/`" model?** Recommended: **no**, keep the template's "list of exempt paths" (`EXEMPT_PREFIXES`). It is the safer default for a pure MCP service; nextrace changed it only because of its admin SPA. Only the `?api_key=` query parameter is worth considering (optional).
- [ ] **D5. Ship dev tools (mock host, smoke script)?** Recommended: **ship the mock host**. Without it, an app can only be debugged by hand in Claude Desktop. The smoke script is optional.
- [ ] **D6. Make `user_role` a template feature?** Recommended: **no**. nextrace's `jwt.py` looks up roles in MongoDB, which is business-specific. The template's `jwt.py` is cleaner as it is.

---

## A. SDK upgrade (required)

### A1. Dependencies
- [ ] `pyproject.toml`: `"mcp[cli]==1.26.0"` → `"mcp[cli]==2.3.0"`; then `uv lock && uv sync`.
  - Verify: `uv.lock` contains `mcp 2.3.0` and `mcp-types 2.3.0`. In nextrace the upgrade added `mcp-types`, `httpx2`, `httpcore2`, `httpx2-jsfetch` and `truststore`, removed `httpx-sse` and `pydantic-settings`, and left FastAPI, Starlette and pydantic unchanged.
  - Note: `mcp.server.fastmcp` is an empty stub in 2.x, and importing it raises `ModuleNotFoundError` directly.

### A2. `src/server.py`: FastMCP → MCPServer
- [ ] Change it to:
```python
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

# Transport settings are passed to streamable_http_app() in src/http/mcp_mount.py
# (mcp 2.x moved them off the constructor).
mcp = MCPServer(
    name=config.SERVICE_NAME,
    # instructions=...,      # see C6
    # extensions=[apps],     # see C1
)

# Must be passed explicitly: when omitted, mcp 2.x auto-enables DNS rebinding
# protection that only allows localhost hosts.
MCP_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
    allowed_hosts=["*"],
    allowed_origins=["*"],
)
```
  - Verify: `python -c "import src.server"` succeeds.

### A3. `src/http/mcp_mount.py`
- [ ] Change it to:
```python
from src.server import MCP_TRANSPORT_SECURITY, mcp
...
    # Path is "/" because the app is mounted at /mcp (2.x defaults to "/mcp",
    # which would yield /mcp/mcp). stateless_http disables session management.
    streamable_app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=MCP_TRANSPORT_SECURITY,
    )
```
  - Keep `MCPPathMiddleware` (`/mcp` → `/mcp/`) unchanged.
  - Verify: both `POST /mcp` and `POST /mcp/` return 200 for `initialize`, with no 307 and no 404. A devtunnel or other non-localhost domain is not rejected.
  - Pitfall: if `transport_security` is left out, the 2.x default host is 127.0.0.1 and DNS rebinding protection is enabled automatically, so requests from public domains get 421/403.

### A4. `src/deps.py`: tool_guard converts exceptions to ToolError (**most important**)
- [ ] mcp 2.x only returns the text of a `ToolError` to the client. Any other exception becomes just `Error executing tool <name>`, so friendly messages such as permission or disabled-resource errors are all lost.
```python
from mcp.server.mcpserver.exceptions import ToolError

        async def wrapper(*args, **kwargs):
            try:
                auth = get_auth()
                for dep in (depends_on or []):
                    await dep(auth)
                await record_tool_call(fn.__name__, auth, _safe_input_summary(kwargs))
                return await fn(*args, **kwargs)
            except ToolError:
                raise
            except Exception as exc:
                # SDK logs ToolError without a traceback; keep it for diagnosis
                logger.warning("Tool %s failed: %s", fn.__name__, exc, exc_info=True)
                raise ToolError(str(exc)) from exc
```
  - Also update the module docstring (explain why it converts) and change "FastMCP can introspect…" to MCPServer.
  - Verify: in restricted mode (`ALLOWED_ENTRA_GROUPS` set, using an API key), calling `ping` returns `isError=true` with the text `...No Entra groups found in token`, not just "Error executing tool ping".
  - Note: Pydantic argument-validation errors still return their full text, so they are unaffected.

### A5. `src/http/app.py`
- [ ] Code: the lifespan `async with mcp.session_manager.run()` still works on 2.x and needs no change. It must run after `streamable_http_app()` is called, which `mount_mcp` already does, the same as 1.x.
- [ ] In comments and docstrings, change FastMCP to MCPServer (`app.py`, `auth_context.py`, `middleware/auth.py`).
  - Verify: start and Ctrl+C both raise no exceptions; `/health` returns 200.

### A6. Known wire-level differences after the upgrade (no fix needed; good to know)
- `serverInfo.version` was `"1.26.0"` (the SDK version) in 1.x and is `""` in 2.x.
- `capabilities.experimental: {}` is no longer returned.
- Wire schemas are unchanged (`inputSchema` and similar keep the same names, even though the Python attributes are snake_case).

---

## B. Syncing general fixes (D1; recommended)

### B1. RFC 9728: well-known with a path suffix (`src/http/well_known.py`)
- [ ] Register two routes on the same handler:
```python
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/{path:path}")
async def oauth_protected_resource(path: str = ""):
    # RFC 9728 §3.1: clients insert the well-known prefix between host and the
    # resource path (/mcp), so serve both forms with the same document.
```
  - `resource` = `{BASE_URL}/mcp`, `authorization_servers` = `[BASE_URL]` (our proxy, not Entra; the template already does this, keep it).
  - Verify: `GET /.well-known/oauth-protected-resource/mcp` returns 200 with the same JSON as the bare route.

### B2. `WWW-Authenticate` points to the path-suffixed metadata (`src/http/middleware/auth.py`)
- [ ] `resource_metadata` must include `/mcp`:
```python
_MCP_PATH = "/mcp"
_RESOURCE_METADATA_URL = (
    f"{config.BASE_URL.rstrip('/')}/.well-known/oauth-protected-resource{_MCP_PATH}"
)
```
  - Verify: `POST /mcp/` without a token → 401, header `WWW-Authenticate: Bearer resource_metadata="{BASE_URL}/.well-known/oauth-protected-resource/mcp"`.
- [ ] (Optional, D4) `api_key` mode also accepts the `?api_key=` query parameter (see the nextrace `auth.py` query_string parsing). Useful for clients that cannot add headers.

### B3. OAuth proxy (`src/http/oauth_proxy.py`)
- [ ] `/register` response: add `"grant_types": body.get("grant_types", ["authorization_code"])`.
- [ ] `/authorize`: make `state` optional (`state: Optional[str] = None`, and pass `state or ""` when forwarding). Some clients do not send it.
- [ ] `/authorize`: scope de-duplication to avoid Entra AADSTS70011:
```python
_required_scope = "access_as_user"
api_scope = f"api://{config.AZURE_CLIENT_ID}/{_required_scope}"
scopes = set(scope.split()) if scope else set()
scopes.discard(_required_scope)   # clients may send the short form too
scopes.add(api_scope)
scopes.add("offline_access")      # ensures a refresh_token is issued
merged_scope = " ".join(sorted(scopes))
```
- [ ] `/token` response: add `resource` so clients such as Postman can associate the token with the MCP endpoint (RFC 8707):
```python
if "access_token" in body:
    body["resource"] = f"{config.BASE_URL.rstrip('/')}/mcp"
```
- [ ] (Optional) Add redirect_uri, scope and has_id_token to the logs to make debugging easier.
  - Verify: the Postman MCP client can authorize and list tools; Claude Desktop and Copilot Studio still connect through DCR.

### B4. stream_guard (`src/http/middleware/stream_guard.py`)
- [ ] `GET /mcp` is a long-lived SSE notification stream, so **do not start the idle watchdog for it** (the hard timeout stays): `is_sse_get = scope.get("method") == "GET"`.
- [ ] `http.response.start` also refreshes `last_sent`; track `response_complete`.
- [ ] Add `_finish_response()`: after a timeout or cancellation, if the response has started but not finished, send `{"type": "http.response.body", "body": b"", "more_body": False}` to close it properly.
  - Copy the whole file from nextrace `src/http/middleware/stream_guard.py` (it has no business coupling).
  - Verify: the `/health` active_streams count returns to 0 after concurrent requests end; an open GET SSE stream is not cut after 60 seconds of idle.
- FYI (not fixed): sse-starlette sends a `: ping` every 15 seconds, which refreshes the idle timer, so a slow request is in practice bounded only by the hard timeout of 300 seconds.

---

## C. MCP App example: `whoami_card` (D2)

### C0. Target structure
```
src/
  apps/
    __init__.py          # exports apps / APP_CALLABLE_META / APPS_INSTRUCTIONS
    app_bridge.js        # (D3) shared host bridge, inlined into each HTML file
    whoami_card.py       # tool + resource registration
    whoami_card.html     # UI (no external resources)
  server.py              # MCPServer(..., extensions=[apps] if config.ENABLE_MCP_APPS else [])
config.py                # ENABLE_MCP_APPS
```

UI sketch:
```
+--------------------------------------------+
|  Signed in as  Jane Doe (jane@corp.com)    |  <- from tool-result structuredContent
|  Auth mode     entra_auth                  |
|  [ Ping server ]   pong at 12:01:03        |  <- iframe calls ping via host tools/call
|  [ Send to chat ]                          |  <- ui/message, only on user click
+--------------------------------------------+
```

### C1. Registration order (**key constraint**)
- [ ] mcp 2.3.0 fixes `extensions` at `MCPServer(...)` construction time (`_apply_extension` is private; source comment: "Extensions are fixed at construction"). **`Apps()` must have all its tools and resources registered before `mcp = MCPServer(...)`**, otherwise they are silently ignored. That is why apps live in a separate module and `server.py` only imports them.
- [ ] `config.py`:
```python
# MCP Apps (interactive UI). Set to "false" to hide app tools/resources from
# clients that mishandle them.
ENABLE_MCP_APPS = os.getenv("ENABLE_MCP_APPS", "true").strip().lower() not in ("false", "0", "no")
```
- [ ] `src/server.py`: `extensions=[apps] if config.ENABLE_MCP_APPS else []`.
  - Verify: when enabled, there is one more tool and one `ui://` resource; when `ENABLE_MCP_APPS=false`, the tool list is identical to before and there are no resources.

### C2. Tool and resource (`src/apps/whoami_card.py`)
- [ ] Key points (see nextrace `extraction_wizard.py`):
```python
from pathlib import Path
from mcp.server.apps import Apps, ResourcePermissions
from mcp_types import CallToolResult, TextContent

CARD_URI = "ui://boilerplate/whoami-card.html"
CARD_TITLE = "Who Am I"                       # display name; hosts otherwise derive it from the tool name
CARD_HTML = load_app_html("whoami_card.html") # (D3) inlines app_bridge.js; read once at import

apps = Apps()
apps.add_html_resource(
    CARD_URI, CARD_HTML, name=CARD_TITLE,
    permissions=ResourcePermissions(clipboard_write={}),
    prefers_border=True,                      # spec recommends an explicit value
)

# "ui/resourceUri" is the legacy flat key older hosts read; the ext-apps SDK sets both.
@apps.tool(resource_uri=CARD_URI, meta={"ui/resourceUri": CARD_URI}, title=CARD_TITLE)
@tool_guard(depends_on=[check_entra_groups])
async def whoami_card() -> CallToolResult:
    """Show the signed-in identity in an interactive card ..."""
    info = ...  # same data as whoami
    return CallToolResult(
        content=[TextContent(type="text", text=f"Signed in as ...")],   # model + no-UI clients
        structured_content=info,                                        # for the UI
    )
```
  - **Return a `CallToolResult`, with the return annotation also set to `CallToolResult`**: MCPServer 2.3.0 passes it through as-is (it is not wrapped as `{"result": ...}`, and no outputSchema is generated). It also works through `tool_guard`. This is the only way to return both "readable text for the model / clients without UI" and "structured data for the UI".
  - **Always include the text content.** `client_supports_apps(ctx)` **is always False in stateless_http mode** (each request is a new session and initialize is not remembered), so you cannot use it to choose the response format.
- [ ] Order of the two decorators: `@apps.tool(...)` on the outside, `@tool_guard(...)` on the inside, the same as `@mcp.tool()`.

### C3. Existing tools the app calls must declare visibility
- [ ] The ext-apps spec says hosts **must reject** a `tools/call` initiated by the app when the target tool's `visibility` does not include `"app"`. The default is `["model","app"]`, but the spec does not say how to treat an ordinary tool with **no `_meta.ui` at all**, so declare it explicitly:
```python
# src/apps/__init__.py
APP_CALLABLE_META = {"ui": {"visibility": ["model", "app"]}} if config.ENABLE_MCP_APPS else None

# src/server.py
@mcp.tool(meta=APP_CALLABLE_META)
@tool_guard(depends_on=[check_entra_groups])
async def ping(...): ...
```
  - The app's tool calls are proxied by the host over the same connector connection with the same Bearer token, so `tool_guard` / group checks **apply automatically**; nothing extra is needed.

### C4. HTML and bridge (`app_bridge.js` + `whoami_card.html`)
The protocol is ext-apps `2026-01-26` (JSON-RPC 2.0 over `window.parent.postMessage`). Hand-written, with no npm or CDN; you can reuse the bridge section at the top of nextrace `extraction_wizard.html` directly.

- [ ] Handshake: send the request `ui/initialize` `{protocolVersion: "2026-01-26", appInfo, appCapabilities: {}}` → apply `hostContext` (`theme`, `styles.variables` such as `--color-text-primary`, `styles.css.fonts`) → send the notification `ui/notifications/initialized`.
  - **The host sends nothing before it receives initialized.**
- [ ] Receive: `ui/notifications/tool-input` (arguments, at most once) → `ui/notifications/tool-result` (CallToolResult, with structuredContent). Also handle `tool-cancelled` and `host-context-changed`.
- [ ] Host → app requests: answer `ui/resource-teardown` with `{}` and **stop all timers or polling**; answer `ping` with `{}`.
- [ ] App → host: `tools/call` (call ping). Unwrap the result like this: `isError` → throw the text; if `structuredContent` contains only `result`, take `.result`; otherwise take `structuredContent`; finally fall back to `JSON.parse(text)`.
- [ ] **Size reporting**: measure `document.body.getBoundingClientRect()` and observe `body` with the ResizeObserver; send `ui/notifications/size-changed {width, height}` (debounced, only when the value changes).
  - **Do not use `documentElement.scrollHeight`**: inside an iframe it is never smaller than the iframe's current height, so the card can only grow, never shrink (nextrace bug, fixed in `aa3a295`).
- [ ] **"Send to chat"**: use `ui/message`, **send only on user click** (never automatically, so you don't interrupt the user). The spec defines `content` as a single object `{type: "text", text}`, but some hosts expect an array, so: send the object first, and if that errors, resend once with `[{type: "text", text}]`; if both fail, show the error and expand the content into a copyable field.
  - Background: `ui/update-model-context` **is not forwarded to the model by Claude Desktop** (testing confirmed this). Do not use it as the only channel; at most use it as a supplement.
- [ ] Opening links: `ui/open-link {url}`; fall back to `<a target="_blank">` on failure.
- [ ] Clipboard: `navigator.clipboard.writeText` may be blocked by the sandbox's permissions policy (the mock host blocks it). On failure, expand a read-only input with the text selected so the user can press Ctrl+C.
- [ ] Rendering: build the DOM with `textContent` throughout (no `innerHTML` with data). `replaceChildren(...view().filter(Boolean))`, otherwise `null` is rendered as the text "null".
- [ ] **Search or input boxes: do not re-render on every keystroke.** Rebuilding the input each time loses focus, scrambles the typed text, and breaks Chinese IME input. Replace only the list being filtered and keep the input element itself.
- [ ] Style: CSS variables plus host variables overriding them; `prefers-color-scheme` dark mode as a fallback; must work at 360px width; keep it compact (13px font, single-line list items).
- [ ] No external resources: `grep -E 'src="https?:|href="https?:|@import' src/apps/*.html` should find nothing. Without `ui.csp`, the default CSP is `default-src 'none'`, inline script/style are allowed, `connect-src 'none'` (the iframe cannot fetch; all data goes through the host's tools/call).
- [ ] (D3) `load_app_html(name)`: read the HTML, then replace a placeholder (such as `/*__APP_BRIDGE__*/`) with the contents of `app_bridge.js`.

### C5. Fallback for clients without UI
- [ ] The text content from `whoami_card` itself must be usable on its own (for example Copilot Studio, which does not render apps). When the tool needs follow-up steps, put in the text "if you cannot display the UI, do X with tools A → B".

### C6. (Optional) Getting the model to choose the app
- [ ] Lesson from nextrace: **descriptions alone are not reliable.** Claude still went straight to the plain tools. If a business needs "use the UI by default", use three layers: `MCPServer(instructions=...)` (set only when apps are enabled) + the app tool description starting with "DEFAULT way to …" + server-side enforcement (nextrace's `skip_form` guard). This is a business decision; the template only needs to **mention the pattern in the README**, not implement the guard.

### C7. Packaging
- [ ] The Dockerfile `COPY src/ ./src/` already includes `.html` and `.js`; check that `.dockerignore` does not exclude them.
  - Verify: inside the container, `resources/read ui://boilerplate/whoami-card.html` returns the complete HTML.

---

## D. Dev tools (D5, optional)

- [ ] **Mock MCP Apps host**: copy from nextrace `scripts/mcp_app_host/` (`serve.py` + `host.html`; it is gitignored in nextrace, so take it from that working copy).
  - Real mode: forwards JSON-RPC to the local MCP server (uses the API key).
  - Mock mode: `?mock=completed|empty|failed|flaky|running|submitError` (business-specific to nextrace; for the template, change it to whoami/ping scenarios), `?theme=dark`, `?width=360`, `?msgArray=1` (simulates a host that only accepts a content array).
  - Records every message in `window.__hostLog`, ready for Playwright assertions; enforces the visibility rule (rejects tools without "app").
  - The template should commit it to the repo (not ignore it) and add usage to the README.
- [ ] (Optional) `scripts/mcp_smoke.py`: raw JSON-RPC snapshot/compare (initialize, tools/list, prompts/list, a few tool calls, well-known/DCR/401 checks), used for regression comparison before and after upgrades. Remove the nextrace business calls from `build_calls()`.

---

## E. Documentation

- [ ] README: FastMCP → "MCP Python SDK 2.x (`MCPServer`)"; add an MCP Apps section (directory structure, registration order constraint, visibility, `ENABLE_MCP_APPS`, how to debug with the mock host, "the HTML is read at import, so restart after editing").
- [ ] `.env.example`: add
```
# MCP Apps (interactive UI rendered by clients such as Claude). Default: true
ENABLE_MCP_APPS=true
```
- [ ] README "Adding a tool" guide: note that tool_guard converts exceptions to ToolError, and that tools an app needs to call must use `meta=APP_CALLABLE_META`.

---

## F. Pitfalls (all hit for real in nextrace)

| # | Symptom | Cause | Solution |
|---|---|---|---|
| 1 | All tool errors became "Error executing tool xxx" | 2.x only forwards ToolError text | A4 |
| 2 | Requests from devtunnel/public domains rejected | 2.x enables DNS rebinding protection when transport_security is omitted | A2/A3 |
| 3 | Route became /mcp/mcp | 2.x defaults to streamable_http_path="/mcp" | A3 `"/"` |
| 4 | App tool registered but missing | Apps registered after MCPServer construction | C1 |
| 5 | `initialize` result has no `capabilities.extensions` | mcp 2.3.0 sends this field only on the 2026-07-28 protocol and filters it out for 2025-06-18/11-25 | No fix needed: hosts discover UI through the tool's `_meta.ui.resourceUri` |
| 6 | `client_supports_apps()` always False | stateless_http does not remember initialize | Always return text + structuredContent (C2) |
| 7 | Model has no execution_id after a task finishes | Claude Desktop does not forward `ui/update-model-context` | "Send to chat" button with ui/message (C4) |
| 8 | Card does not shrink with content | Measured documentElement.scrollHeight | Measure body (C4) |
| 9 | Search box scrambles typed text / IME breaks | Input rebuilt on every keystroke | Replace only the list (C4) |
| 10 | Page shows "null" | replaceChildren receives null | `.filter(Boolean)` |
| 11 | No change after editing the HTML | HTML read at import; `--reload` watches only .py | Restart, or touch a .py file |
| 12 | A running background job was cancelled with an empty error message | Editing a .py file triggered `--reload`, CancelledError stringifies to "" | Do not edit source while a job runs; write errors with `str(e) or type(e).__name__` |
| 13 | Claude bypasses the UI and calls plain tools directly | Descriptions only nudge the model | C6 three-layer guidance + server-side enforcement |
| 14 | Download links do not open inside the iframe | sandbox navigation restrictions | `ui/open-link`, falling back to `<a target=_blank>` |

---

## G. Acceptance checklist

- [ ] `uv sync`, then `python -c "import src.server"` succeeds; existing tests pass.
- [ ] Locally, `api_key` mode: `initialize`, `tools/list` (whoami, ping, whoami_card), `resources/read` (mimeType `text/html;profile=mcp-app`), and `tools/call ping` all OK.
- [ ] Restricted mode (`ALLOWED_ENTRA_GROUPS` set): tool errors show readable text (A4); the app card also shows the permission error.
- [ ] OAuth: both `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp` return 200; 401 responses carry the correct `resource_metadata`; DCR `/register` → `/authorize` → `/token` completes.
- [ ] Mock host: handshake, ping, Send to chat (including the `msgArray=1` fallback), teardown, dark mode and 360px all OK; reported height shrinks with content.
- [ ] `ENABLE_MCP_APPS=false`: tool and resource lists are identical to the pre-upgrade version.
- [ ] Docker: the image contains the HTML/JS; `resources/read` inside the container returns the complete HTML.
- [ ] Real clients:
  - [ ] Claude Desktop: DCR + Entra login; `whoami_card` renders; Ping works; Send to chat makes Claude reply.
  - [ ] Claude web: same as above.
  - [ ] Copilot Studio: connection unaffected; whoami_card returns usable text.
  - [ ] Postman MCP client: RFC 9728 discovery + authorization succeed, tools are listed.
