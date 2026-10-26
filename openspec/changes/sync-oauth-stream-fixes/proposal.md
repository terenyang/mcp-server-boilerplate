## Why

Services built from the template have hit client-compatibility problems that the nextrace service already fixed: some clients (Postman, Copilot Studio) register with other grant types, omit `state` on `/authorize`, or keep an SSE `GET /mcp` stream open longer than the idle timeout. The template already carries most of the nextrace OAuth fixes, but two small gaps remain, `stream_guard` still lacks the SSE and response-finishing fixes, and none of this behavior is covered by tests, so it can regress silently.

## What Changes

- `/register` echoes the client's requested `grant_types` (default `["authorization_code"]`) instead of always returning `["authorization_code"]`.
- `/authorize` accepts requests without `state` and forwards an empty `state` to Entra.
- `stream_guard`: a `GET` request (the long-lived SSE notification stream) is exempt from the idle timeout but still bound by the hard timeout.
- `stream_guard`: a response that has started but not finished when a timeout or cancellation hits is closed properly (empty final body, `more_body=False`) instead of being cut off.
- `stream_guard`: `http.response.start` counts as activity for the idle timer.
- Add tests that pin the OAuth behavior the template already has (path-suffixed protected-resource metadata, `resource_metadata` in `WWW-Authenticate`, scope de-duplication with `offline_access`, `resource` in the token response) together with the new behavior above.
- Out of scope: switching auth to the nextrace model that protects only `/api/` and `/mcp/` (D4 in the handoff), the optional `?api_key=` query parameter, `user_role` (D6), and the MCP App example.

## Capabilities

### New Capabilities
- `oauth-discovery-and-proxy`: protected-resource metadata, 401 challenges, dynamic client registration, and the authorize and token proxy that bridges clients to Entra.
- `mcp-stream-guard`: concurrency cap and timeout behavior for MCP HTTP requests, including SSE streams and cleanly terminated responses.

### Modified Capabilities

None. The existing main specs (`mcp-http-transport`, `tool-error-reporting`) are unaffected.

## Impact

- Code: `template/src/http/oauth_proxy.py`, `template/src/http/middleware/stream_guard.py`; new tests under `template/tests/`.
- Wire behavior: `/register` response `grant_types` may now differ from `["authorization_code"]`; `/authorize` no longer returns 422 when `state` is missing; long-lived `GET /mcp` streams are no longer cut at the idle timeout.
- No dependency or configuration changes.
