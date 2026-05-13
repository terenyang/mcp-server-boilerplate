# MCP Server Boilerplate — System Design

## Table of Contents

1. [Overview](#overview)
2. [Request Flow](#request-flow)
3. [Authentication](#authentication)
4. [OAuth 2.0 Proxy](#oauth-20-proxy)
5. [MCP Tool Execution](#mcp-tool-execution)
6. [Deployment](#deployment)
7. [Known Limitations & Future Work](#known-limitations--future-work)

---

## Overview

This boilerplate exposes domain-specific functionality via the [Model Context Protocol](https://modelcontextprotocol.io/). It acts as an MCP **resource server** (OAuth 2.1 terminology) that clients such as Claude.ai, Copilot Studio, and Claude Desktop can connect to with natural-language queries.

**Core responsibilities:**

| Layer | Responsibility |
|---|---|
| HTTP / Auth | FastAPI + Starlette middleware; JWT (`middleware/jwt.py`) or API key (`middleware/api_key.py`) validation |
| OAuth proxy | Bridges Claude.ai's RFC 7591 DCR requirement with Azure Entra's static app model |
| MCP protocol | FastMCP streamable-HTTP transport; stateless mode |

---

## Request Flow

### Normal MCP Request (authenticated)

```
Client
  │
  │  POST /mcp  Authorization: Bearer {jwt}
  ▼
AuthenticationMiddleware
  │  1. Exempt paths bypass (/.well-known, /docs, /register, /authorize, /token)
  │  2. Bearer header → middleware/jwt.authenticate()
  │       a. Fetch JWKS from Entra (cached 1 h)
  │       b. Verify RS256 signature
  │       c. Validate aud ∈ {api://{client_id}, {client_id}, BASE_URL}
  │       d. Validate iss ∈ {v2 issuer, v1 issuer}
  │       e. Require oid claim (user object ID)
  │  3. Fallback: x-api-key header → middleware/api_key.ensure_valid_api_key()
  │
  ▼
MCPPathMiddleware
  │  Rewrites /mcp → /mcp/ to prevent Starlette 307 redirect on POST
  │
  ▼
StreamConcurrencyController  (wraps FastMCP ASGI app)
  │  • Semaphore: max 20 concurrent streams (configurable)
  │  • Queue wait: 5 s → 429 if exceeded
  │  • Idle timeout: 60 s → 503 if no data sent
  │  • Hard timeout: 300 s → 503 regardless
  │
  ▼
FastMCP (streamable HTTP)
  │  • MCP Initialize → tool list
  │  • MCP tool_call → dispatched to tool handler in src/server.py
  │
  ▼
Tool handler (src/server.py)
  │  • Validates parameters
  │  • Calls service layer
  │  • Returns structured JSON
```

### First-time Request (unauthenticated — triggers OAuth discovery)

```
Client  POST /mcp  (no token)
  ▼
AuthenticationMiddleware
  └─ Returns 401 + WWW-Authenticate: Bearer resource_metadata="{BASE_URL}/.well-known/oauth-protected-resource"

Client  GET /.well-known/oauth-protected-resource
  └─ Returns: resource, authorization_servers, scopes_supported

Client  GET /.well-known/oauth-authorization-server
  └─ Returns: issuer, authorization_endpoint, token_endpoint, registration_endpoint

Client → OAuth flow → token → retry POST /mcp with Bearer token
```

---

## Authentication

Two schemes are accepted, checked in order:

### 1. JWT Bearer (Azure Entra)

`src/http/middleware/jwt.py` validates access tokens issued by Azure AD / Entra ID.

**Accepted audiences** (token `aud` claim must match one of):
- `api://{AZURE_CLIENT_ID}` — standard Azure App ID URI
- `{AZURE_CLIENT_ID}` — raw GUID (ID tokens)
- `{BASE_URL}` — canonical server URI

**Accepted issuers** (token `iss` claim must match one of):
- `https://login.microsoftonline.com/{AZURE_TENANT_ID}/v2.0` — user tokens (v2)
- `https://sts.windows.net/{AZURE_TENANT_ID}/` — app/client-credential tokens (v1)

**JWKS caching:** Keys fetched from `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys`, cached for 1 hour. Falls back to stale cache on fetch failure.

### 2. API Key

`x-api-key` header checked in `src/http/middleware/api_key.py` against the `API_KEYS` environment variable (comma-separated list). Intended for server-to-server or development use.

---

## OAuth 2.0 Proxy

Claude.ai and similar clients require [RFC 7591 Dynamic Client Registration](https://datatracker.ietf.org/doc/html/rfc7591) before they can start an OAuth flow. Azure Entra does not support DCR. The OAuth proxy in `src/http/oauth_proxy.py` bridges this gap.

### Discovery Chain

```
RFC 9728: /.well-known/oauth-protected-resource
  resource:              "https://{BASE_URL}/mcp"
  authorization_servers: ["https://{BASE_URL}"]
  scopes_supported:      ["openid", "profile", "email", "offline_access"]
    ↑ api://xxx/access_as_user intentionally OMITTED — see Scope Injection below

RFC 8414: /.well-known/oauth-authorization-server
  issuer:                "https://{BASE_URL}"   ← must match fetch origin (RFC 8414 §3)
  authorization_endpoint "https://{BASE_URL}/authorize"
  token_endpoint:        "https://{BASE_URL}/token"
  registration_endpoint: "https://{BASE_URL}/register"
  scopes_supported:      ["openid", "profile", "email", "offline_access"]
    ↑ NO jwks_uri and NO api:// scopes — prevents Entra detection (see below)
```

### RFC 7591 Dynamic Client Registration (DCR)

Platforms such as Claude.ai and Copilot Studio require a server to support [RFC 7591 DCR](https://datatracker.ietf.org/doc/html/rfc7591) before they will initiate an OAuth flow. DCR allows the client to self-register and obtain credentials without manual configuration. The MCP spec mandates this for "Dynamic Discovery Authentication".

#### What the server must provide

| Requirement | Implementation |
|---|---|
| `POST /register` endpoint | `src/http/oauth_proxy.py` → `dynamic_client_registration()` |
| `registration_endpoint` advertised in AS metadata | `/.well-known/oauth-authorization-server` → `"registration_endpoint"` |
| Accept `application/json` body with `redirect_uris`, `client_name`, `grant_types` | All fields read from request body |
| Return `client_id`, `client_secret`, `client_id_issued_at`, `redirect_uris`, `grant_types`, `response_types`, `token_endpoint_auth_method` | Returned in 201 response |
| `token_endpoint_auth_method: "none"` | Signals to client that it is a public client; client should use PKCE instead of a client secret at `/token` |

#### Request / Response

```
POST /register
Content-Type: application/json

{
  "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
  "client_name": "Claude",
  "grant_types": ["authorization_code"]
}

HTTP/1.1 201 Created
{
  "client_id": "dynamic-<random-22-chars>",
  "client_secret": "<random-43-chars>",
  "client_id_issued_at": 1715000000,
  "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none"
}
```

The returned `client_id` is used by the client in subsequent `/authorize` and `/token` calls. The proxy replaces it with `AZURE_CLIENT_ID` before forwarding to Entra — the synthetic credentials are never sent to Entra.

> **In-memory store:** registered clients are held in `_registered_clients` dict (per-process). A server restart or load-balancer routing `/register` and `/authorize` to different instances will break the flow. For multi-instance deployments, back this with Redis or MongoDB.

### Why `api://` Scopes Are Hidden in Discovery

If `api://{client_id}/access_as_user` appears in `scopes_supported`, Claude.ai detects the Azure-specific scope pattern and bypasses the proxy, sending requests directly to Entra's `/oauth2/v2.0/authorize` endpoint with a `resource` parameter. Azure Entra v2 rejects the `resource` parameter with `AADSTS9010010`.

By hiding the Azure scope from discovery metadata and injecting it in the proxy, clients see a generic OAuth 2.0 server and route through our proxy.

### Full OAuth Flow — Claude.ai / Claude Desktop

```
1. Claude     POST /register
              {"redirect_uris": ["https://claude.ai/api/mcp/auth_callback"], ...}

   Server     Issues synthetic client_id ("dynamic-xxx"), stores in memory
   Response   {"client_id": "dynamic-xxx", "token_endpoint_auth_method": "none"}

2. Claude     GET /authorize
              ?client_id=dynamic-xxx (or real AZURE_CLIENT_ID if user pre-configured it)
              &scope=openid+profile+email+offline_access   ← sent by Claude
              &resource=https://{BASE_URL}/mcp              ← RFC 8707 resource indicator
              &code_challenge=...&code_challenge_method=S256
              &redirect_uri=https://claude.ai/api/mcp/auth_callback
              &state=...

   Proxy      a. Swaps client_id → AZURE_CLIENT_ID
              b. Injects scope: adds api://xxx/access_as_user + offline_access
              c. Drops resource parameter (Entra v2 rejects it)
              d. 302 → Entra /oauth2/v2.0/authorize

3. User authenticates at Entra login page, grants consent

4. Entra      302 → https://claude.ai/api/mcp/auth_callback?code=xxx&state=...

5. Claude     POST /token
              grant_type=authorization_code, code=xxx
              redirect_uri=https://claude.ai/api/mcp/auth_callback
              code_verifier=... (PKCE)
              resource=https://{BASE_URL}/mcp              ← present in body too

   Proxy      a. Swaps client_id → AZURE_CLIENT_ID
              b. Drops any incoming client_secret, injects AZURE_CLIENT_SECRET
              c. Drops resource parameter
              d. Forwards to Entra /oauth2/v2.0/token

6. Entra      Returns {access_token, id_token, refresh_token, expires_in, scope}
   Token      access_token.aud = "api://xxx"  ✓ matches valid_audiences
              access_token.iss = "https://sts.windows.net/{tenant}/"  ✓

7. Claude     POST /mcp  Authorization: Bearer {access_token}
   Server     JWT validation passes → MCP request processed
```

### Full OAuth Flow — Copilot Studio

Copilot Studio uses the same DCR proxy path but with two behavioural differences: it omits `scope` from the authorize request, and uses a platform-managed redirect URI.

```
1. Copilot Studio  POST /register
                   {"redirect_uris": ["https://global.consent.azure-apim.net/redirect/{id}"], ...}

   Server          Issues synthetic client_id ("dynamic-xxx"), stores in memory
   Response        {"client_id": "dynamic-xxx", "token_endpoint_auth_method": "none"}

2. Copilot Studio  GET /authorize
                   ?client_id=dynamic-xxx
                   &code_challenge=...&code_challenge_method=S256
                   &redirect_uri=https://global.consent.azure-apim.net/redirect/{id}
                   &state=...
                   ← NO scope parameter sent

   Proxy           a. Swaps client_id → AZURE_CLIENT_ID
                   b. scope is None → starts from empty set
                   c. Injects: api://xxx/access_as_user + offline_access
                   d. 302 → Entra /oauth2/v2.0/authorize

3. User authenticates at Entra login page

4. Entra           302 → https://global.consent.azure-apim.net/redirect/{id}?code=xxx
                   ← This URI must be pre-registered in Azure App Registration

5. Copilot Studio  POST /token  (same as Claude flow, steps 5-7)
```

> **Redirect URI registration:** `https://global.consent.azure-apim.net/redirect/{connector-id}` is unique per Copilot Studio connector. The `{connector-id}` is generated by the platform. Copy the exact URI from the browser address bar when the authorization page opens and add it to App Registration → Authentication → Web platform before the first successful login.

### Azure App Registration Requirements

| Setting | Value | Required for |
|---|---|---|
| Redirect URI (Web) | `https://claude.ai/api/mcp/auth_callback` | Claude.ai web |
| Redirect URI (Web) | `https://global.consent.azure-apim.net/redirect/{connector-id}` | Copilot Studio (unique per connector — add after first connection attempt) |
| Redirect URI (Mobile/desktop) | `http://localhost` | Claude Desktop |
| Expose an API → scope | `access_as_user` → full URI: `api://{AZURE_CLIENT_ID}/access_as_user` | All OAuth clients |
| `AZURE_CLIENT_SECRET` (server env) | Client secret from Certificates & secrets | Confidential client token exchange (recommended) |
| Allow public client flows | Yes | Only if `AZURE_CLIENT_SECRET` is not set (PKCE-only mode) |

### Multi-Instance Caveat

`_registered_clients` (DCR store) is in-memory per process. In a multi-instance deployment, `/register` and `/authorize` could hit different instances, breaking the flow. Fix: move the store to Redis or MongoDB.

---

## MCP Tool Execution

All tools are defined in `src/server.py` and registered on a FastMCP instance in stateless HTTP mode.

### Adding Tools

```python
@mcp.tool()
async def my_tool(param: str) -> dict:
    """Tool description shown to the LLM."""
    auth = get_auth()   # AuthContext with JWT claims or api_key sentinel
    # ... your logic here
    return {"result": ...}
```

### Tool Call Path

```
FastMCP tool_call dispatch
  → src/server.py handler
      ├── Parameter validation
      ├── Service / business logic call
      └── Return structured JSON response
```

### Auth Context in Tools

`get_auth()` returns an `AuthContext` (from `src/auth_context.py`) set by the middleware. It is propagated via Python `contextvars` — no explicit passing needed.

| Field | Bearer (JWT) | API Key |
|---|---|---|
| `auth_type` | `"bearer"` | `"api_key"` |
| `user_oid` | Azure AD object ID | `None` |
| `user_name` | Display name | `None` |
| `user_upn` | UPN (email) | `None` |

---

## Deployment

### Docker Compose (local / staging)

```
mcp-server (port 8080)
```

`docker-compose.yml` defines the service. The container uses a multi-stage Dockerfile:

1. Install Python dependencies via `uv`
2. Copy application source
3. Entrypoint: `uvicorn main:app --host 0.0.0.0 --port 8080`

### Azure App Service

```
Azure App Service (container)
  ├── Pull image from Azure Container Registry
  ├── Environment variables from App Service Configuration
  └── Port 8080 exposed via WEBSITES_PORT

External dependencies:
  └── Azure Entra (App Registration for OAuth)
```

**Health probe:** `GET /health` — returns 200 with memory and stream metrics.

### Microsoft DevTunnels (development)

For testing Claude.ai OAuth locally:
```bash
devtunnel host -p 8080 --allow-anonymous
# Tunnel URL: https://xxxx-8080.use.devtunnels.ms
```

Set `BASE_URL=https://xxxx-8080.use.devtunnels.ms` in `.env`.

---

## Known Limitations & Future Work

### Security

| Issue | Status | Notes |
|---|---|---|
| CORS configured as `allow_origins=["*"]` | Open | Restrict to known client origins in production |
| OAuth DCR store is in-memory (lost on restart) | Open | Persist to Redis or MongoDB for multi-instance |
| JWT key cache has no write lock (race on parallel requests) | Low | Add `asyncio.Lock` around cache update |

### Reliability

| Issue | Status | Notes |
|---|---|---|
| Stream concurrency enforced | Done | `StreamConcurrencyController` with semaphore + timeouts |

### Developer Experience

| Issue | Notes |
|---|---|
| No structured logging / request tracing | Add correlation ID middleware; use `structlog` |
