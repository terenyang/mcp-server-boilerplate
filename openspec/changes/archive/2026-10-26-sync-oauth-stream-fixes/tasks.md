## 1. OAuth tests for existing behavior

- [x] 1.1 Add `template/tests/test_oauth.py` with tests for both protected-resource metadata URLs (200, identical bodies, `resource` ends with `/mcp`) and for the 401 `WWW-Authenticate` header on `POST /mcp/` without credentials; verify they pass against the current code
- [x] 1.2 Add tests for `/authorize` scope handling (`follow_redirects=False`, parse `Location`): short scope name plus `openid` yields the full `api://` scope once, no short name, and keeps `openid` and `offline_access`; verify they pass against the current code
- [x] 1.3 Add `/token` tests with a fake `httpx.AsyncClient` patched into `src.http.oauth_proxy`: a 200 response with `access_token` gains `resource` equal to `<BASE_URL>/mcp`, and a non-200 response is passed through with the same status and body without `resource`; verify they pass against the current code

## 2. OAuth gaps

- [x] 2.1 Add failing tests for `/register` (requested `grant_types` echoed; default `["authorization_code"]`) and for `/authorize` without `state` (302 to Entra) and with `state` (same value in `Location`); verify the missing-`state` and non-default `grant_types` tests fail before the change
- [x] 2.2 In `template/src/http/oauth_proxy.py` echo `body.get("grant_types", ["authorization_code"])` in `/register`, and make `state` optional in `/authorize` forwarding `state or ""`; update the module docstring if needed; verify the tests from 2.1 pass

## 3. stream_guard

- [x] 3.1 Add `template/tests/test_stream_guard.py` that drives `StreamConcurrencyController` directly with fake ASGI apps, covering: 429 with `Retry-After` when the cap is exceeded and slot release afterwards (`_active_streams` back to 0); idle POST cancelled and answered with 503 `mcp_stream_timeout`; idle GET after `http.response.start` stays open past the idle timeout; GET closed at the hard timeout; started-but-unfinished response receives a final empty body with `more_body` false after cancellation; response start refreshing the idle timer (app delays 1.2 s before start and 1.2 s before body with idle 1.5 s); verify the GET exemption, clean-termination and response-start tests fail on the current code
- [x] 3.2 In `template/src/http/middleware/stream_guard.py` track `response_complete`, refresh `last_sent` on `http.response.start`, skip the idle watchdog for `GET`, add `_finish_response()` (suppressing send errors) on cancellation and in `finally`; verify all tests in `test_stream_guard.py` pass and the active-stream count returns to 0 in every scenario

## 4. Acceptance

- [x] 4.1 Run the full test suite in `template/` and verify everything passes, including the earlier 25 tests
- [x] 4.2 Start the app locally, open `GET /mcp` with an API key and an `Accept: text/event-stream` header, keep it open longer than `IDLE_STREAM_TIMEOUT` (set to 3 s for the check) and verify it is not closed; verify `/health` shows `active_streams` returning to 0 after it is closed
- [x] 4.3 In `template/.env.example` comment the stream settings to say `GET /mcp` SSE streams are exempt from `IDLE_STREAM_TIMEOUT` and bounded by `HARD_STREAM_TIMEOUT`; verify the comment sits beside those settings
