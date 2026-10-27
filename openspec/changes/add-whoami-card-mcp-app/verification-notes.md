# Verification notes

Recorded while applying `add-whoami-card-mcp-app` (2026-10-26). Browser checks were run with Playwright against the mock host (`template/scripts/mcp_app_host/`), with the MCP server running locally on port 8099 using an API key. They are not part of the default `pytest` run.

## Spike (task 1.1), mcp 2.3.0

| Question | Result |
|---|---|
| `Apps()` populated before `MCPServer(extensions=[apps])` | tool and resource are exposed |
| `Apps()` populated after construction | silently ignored (`tools=[]`, `resources=[]`) |
| `ResourcePermissions(clipboard_write={})` | accepted; `clipboardWrite={}` also accepted; serialized as `clipboardWrite` |
| `CallToolResult` through `tool_guard` | returned unchanged, no output schema; `_meta` has both `ui/resourceUri` and `ui.resourceUri` |

## Mock host checks (task 5.2)

| Check | Result |
|---|---|
| Real mode (task 5.1): handshake, render against the live server | card rendered from the server's result; host sent nothing before `ui/notifications/initialized`; reported size 640x167 |
| Ping in real mode | app sent `tools/call ping`, host proxied it, card showed `pong: 'card' at ...` |
| Bearer scenario | shows name, UPN, auth mode, object ID; height 190 |
| API-key scenario | shows "API key (no user)"; height 167 |
| `denied` | the card is replaced by "User is not authorized to access this tool"; no Ping button |
| `pingdenied` | card stays; Ping shows the same error text |
| Send to chat is user-initiated | 0 chat messages after load and after 3 s; exactly 1 after the click, content sent as a single object |
| `msgArray=1` | first request (object) rejected with "Invalid message format", automatic retry as an array accepted |
| `msgFail=1` | both attempts rejected; card shows the error, a focused read-only text box with the message selected, and a Copy button; height grew 190 to 328 |
| Height follows content | after hiding the fallback block inside the frame, the app reported 190 and the iframe went from 328px to 190px |
| Visibility rule | app call to `model_only_tool` rejected by the host: "Tool not callable by app" |
| Teardown | app replied `{"id":1000000,"result":{}}`; a later Ping click no longer updated the UI |
| Dark theme | `data-theme=dark`, body background `rgb(28, 31, 36)` |
| 360 px width | iframe 360 px wide, no horizontal overflow, reported 360x190 |

Notes:
- One Playwright click returned "ref not found" although the click had been performed (the chat message was sent). A fresh page showed 0 messages without a click, so the message came from the click, not from the app.
- After teardown the Ping button still sends a call to the host; only the result is ignored. A real host removes the iframe.

## Docker (task 7.2)

Image built from `template/Dockerfile` and run with an API key. There is no `.dockerignore`, and `COPY src/ ./src/` carries the HTML and JS.

| Check | Result |
|---|---|
| Files in the image (`/app/src/apps`) | `app_bridge.js`, `loader.py`, `whoami_card.html`, `whoami_card.py`, `__init__.py` |
| `tools/list` | `whoami_card`, `whoami`, `ping`, `server_profile` |
| `resources/read` of the `ui://` resource | MIME `text/html;profile=mcp-app`, 15161 characters, starts with `<!doctype html>`, ends with `</html>`, bridge inlined (`window.McpApp` present), no placeholder left |
| `tools/call whoami_card` (curl, from the host via 127.0.0.1) | HTTP 200 in about 15 ms with the API-key text and structured content |
| Same call from inside the container | HTTP 200 in about 2 ms |

Note: PowerShell's `Invoke-WebRequest` hung for 20 seconds on `tools/call` responses (it read `tools/list` and `resources/read` fine), although the container log showed `POST /mcp 200` and curl completed in milliseconds. This was a client-side effect in that shell; the cause was not investigated further. Use curl or a Python client when checking the container by hand.

## Still manual (task 7.3)

Not covered by any check above. Do not treat these as done:

- Claude Desktop: DCR and Entra login, `whoami_card` renders, Ping works, Send to chat makes Claude reply.
- Claude web: same as above.
- Copilot Studio: connection unaffected, `whoami_card` returns usable text.
- Postman MCP client: RFC 9728 discovery and authorization succeed, tools are listed.
- A real Entra Bearer token against `ALLOWED_ENTRA_GROUPS` (tests patch `authenticate`).
