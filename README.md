# MCP Server Boilerplate

A minimal MCP server template with dual authentication (OAuth2 via Azure Entra + API key) and two starter tools. Built with Python, FastMCP, and FastAPI.

## Quick Start

**Local dev:**
```bash
uv sync
cp .env.example .env    # fill in required values
python dev.py           # hot-reload on :8080
```

**Docker:**
```bash
cp .env.example .env
docker-compose up -d
curl http://localhost:8080/health
```

## Configuration

| Variable | Required | Description |
|---|---|---|
| `BASE_URL` | Yes | Public URL of this server, no trailing slash |
| `API_KEYS` | Yes | Comma-separated API keys for `x-api-key` auth |
| `AZURE_TENANT_ID` | OAuth2 | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | OAuth2 | Azure App Registration client ID |

Set `BASE_URL=http://localhost:8080` and leave the Azure vars blank to run in API-key-only mode.

## Authentication

| Scheme | Header | Notes |
|---|---|---|
| **OAuth 2.0 (Azure Entra)** | `Authorization: Bearer {jwt}` | Claude.ai, Copilot Studio |
| **API Key** | `x-api-key: {key}` | Server-to-server, local dev |

Public paths (no auth): `/`, `/health`, `/.well-known/*`, `/docs`, `/authorize`, `/token`, `/register`

## MCP Tools

| Tool | Description |
|---|---|
| `whoami` | Returns JWT claims (name, UPN, OID) if OAuth2; message if API key |
| `ping` | Echoes a message back with a server timestamp |

## Connecting Claude.ai web / desktop

1. Open Claude.ai or Claude Desktop → add a new MCP server
2. **MCP URL:** `https://your-host.com/mcp`
3. **Auth type:** OAuth 2.0
4. **Client ID:** your `AZURE_CLIENT_ID`
5. **Client Secret:** leave blank — `AZURE_CLIENT_SECRET` is a server-side env var used by the proxy, not a connector credential

OAuth endpoints are auto-discovered via `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`.

**Azure App Registration requirements:**
- Redirect URI: `https://claude.ai/api/mcp/auth_callback` (Web platform)
- Redirect URI: `http://localhost` (Mobile and desktop applications)
- Enable **"Allow public client flows"** (Authentication tab → Advanced settings)

See `docs/CLIENT_INTEGRATION.md` for full setup instructions and how other clients (Copilot Studio, API key) can connect.

## Adding Your Own Tools

Edit `src/server.py`:

```python
@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description shown to the LLM."""
    auth = get_auth()   # AuthContext or None
    # ... your logic
    return "result"
```

`get_auth()` returns an `AuthContext` with:
- `auth_type`: `"bearer"` or `"api_key"`
- `user_oid`, `user_name`, `user_upn`: populated when `auth_type == "bearer"`

## Architecture

```
HTTP Request
  → AuthenticationMiddleware     JWT or x-api-key; sets AuthContext via ContextVar
  → MCPPathMiddleware            /mcp → /mcp/ rewrite (prevents 307 loop)
  → FastAPI router
       ├── /                     service info
       ├── /health               metrics
       ├── /.well-known/*        OAuth discovery (RFC 8414, RFC 9728)
       ├── /register /authorize /token   OAuth proxy to Entra
       └── /mcp                  FastMCP streamable-HTTP
```
