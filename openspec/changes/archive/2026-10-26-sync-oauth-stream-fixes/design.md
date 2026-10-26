## Context

See proposal.md for motivation. All paths below are under `template/`.

The template already serves path-suffixed protected-resource metadata, sends a path-suffixed `resource_metadata` in `WWW-Authenticate`, de-duplicates scopes in `/authorize`, and adds `resource` to the token response. What is missing is `grant_types` passthrough in `/register`, optional `state` in `/authorize`, and two behaviors in `src/http/middleware/stream_guard.py`: no idle-timeout exemption for SSE `GET`, and no clean termination of a started-but-unfinished response.

The reference implementation is `src/http/middleware/stream_guard.py` in the nextrace repo (commit `4b289af`), which has no business coupling. It was read directly rather than taken from the handoff text.

Verified here: with `stateless_http=True` on mcp 2.3.0, `GET /mcp` opens a long-lived SSE stream (a probe request did not return within 20 seconds), so the idle timeout would otherwise cut it.

## Goals / Non-Goals

**Goals:**
- Close the three gaps without changing any other OAuth or timeout behavior.
- Cover the whole OAuth and stream-guard contract with tests that do not need Entra or a real network.

**Non-Goals:**
- Changing the exempt-path model of `AuthenticationMiddleware` (handoff D4) or adding the `?api_key=` query parameter.
- Persisting the DCR client store (it stays in memory, as the file already documents).
- Making idle detection independent of SSE keep-alive pings (see Risks).

## Decisions

**D1. Port the nextrace `stream_guard` structure rather than redesign it.**
Track `response_started` and `response_complete` in the send wrapper, refresh `last_sent` on `http.response.start`, skip creating the idle watchdog when the method is `GET`, and add `_finish_response()` that sends an empty final body when a response started but did not finish. It runs on cancellation and again in `finally`, where it is a no-op if the response is already complete.
Alternative: apply a different timeout policy per path. Rejected: method is what distinguishes the SSE stream from request/response calls in the streamable-HTTP transport, and the nextrace version has run in production.

**D2. `_finish_response` swallows send errors.**
If the client has already disconnected, `send` raises; the guard's job at that point is cleanup, so the exception is suppressed. Slot accounting is in the outer `finally` and is unaffected.

**D3. Missing `state` is forwarded as an empty string.**
`state` becomes `Optional[str] = None` and the redirect carries `state or ""`. Some clients omit it; Entra accepts an empty value. Alternative: omit the parameter when absent. Rejected because it deviates from the proven nextrace behavior without a known benefit.

**D4. `/register` echoes `grant_types` but the token proxy is unchanged.**
Registration is a shim over a single Entra app, so echoing is only about satisfying clients that validate the response against their request. The token proxy already forwards `grant_type` (including `refresh_token`) to Entra unchanged.

**D5. Tests drive the real pieces without Entra.**
- OAuth: use the shared `mcp_client`. `/authorize` is called with `follow_redirects=False` and its `Location` parsed. `/token` is tested by monkeypatching `httpx.AsyncClient` in `oauth_proxy` with a fake that returns a canned Entra response. `config` values are patched with `monkeypatch`; `_ENTRA_*` URLs are module constants and are asserted by prefix only.
- Stream guard: test `StreamConcurrencyController` directly as an ASGI callable with small fake apps and short timeouts, collecting the messages sent. No server or network is needed. Timeout tests use values of a few seconds at most because the idle watchdog polls once per second.

## Risks / Trade-offs

- [sse-starlette sends a keep-alive ping about every 15 seconds on SSE responses, which refreshes the idle timer] -> Not fixed here. In practice a slow POST is bounded by the hard timeout (300 s default) rather than the idle timeout. Documented in the design only; tests use fake apps so they are not affected.
- [`GET` exemption lets a stuck stream live until the hard timeout] -> The hard timeout still applies and the concurrency cap bounds the cost; both are tested.
- [Timing-based tests can be flaky] -> Use generous margins (idle 1.5 s, assertions after 2 to 3 s) and keep each test independent; if CI proves flaky, the watchdog poll interval can be injected, which is a small follow-up.
- [Echoing `grant_types` could advertise grants the proxy cannot serve] -> Acceptable: unsupported grants fail at Entra's token endpoint with a clear error, same as before.

## Migration Plan

Single commit; no configuration or data migration. Rollback is a revert.
