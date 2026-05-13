"""OAuth 2.0 proxy — bridges Azure Entra with RFC 7591 Dynamic Client Registration.

Azure Entra doesn't support DCR, which Claude requires before starting an OAuth
flow. This proxy handles that gap:

  POST /register   — issues synthetic client credentials; stores in memory
  GET  /authorize  — swaps the dynamic client_id for the real Entra client_id
                     and redirects the browser to Entra
  POST /token      — swaps dynamic credentials for real Entra credentials and
                     proxies the code exchange to Entra's token endpoint

Azure App Registration requirements:
  - Add redirect URI https://claude.ai/api/mcp/auth_callback  (Web platform)
  - Add redirect URI http://localhost  (Mobile/desktop applications)
  - Enable "Allow public client flows" for PKCE support
"""
import base64
import logging
import secrets
import time
import urllib.parse
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

import config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["oauth"])

_ENTRA_BASE = f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}"
_ENTRA_AUTHORIZE = f"{_ENTRA_BASE}/oauth2/v2.0/authorize"
_ENTRA_TOKEN = f"{_ENTRA_BASE}/oauth2/v2.0/token"

# In-memory DCR store — replace with Redis/DB for multi-instance deployments
_registered_clients: dict[str, dict] = {}


@router.post("/register", status_code=201)
async def dynamic_client_registration(request: Request):
    """RFC 7591 Dynamic Client Registration shim."""
    body = await request.json()

    client_id = f"dynamic-{secrets.token_urlsafe(16)}"
    client_secret = secrets.token_urlsafe(32)

    _registered_clients[client_id] = {
        "client_secret": client_secret,
        "redirect_uris": body.get("redirect_uris", []),
        "client_name": body.get("client_name", "Unknown Client"),
    }

    logger.info(
        "DCR: registered client=%s name=%s redirect_uris=%s",
        client_id,
        body.get("client_name"),
        body.get("redirect_uris"),
    )

    return JSONResponse(
        status_code=201,
        content={
            "client_id": client_id,
            "client_secret": client_secret,
            "client_id_issued_at": int(time.time()),
            "redirect_uris": body.get("redirect_uris", []),
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )


@router.get("/authorize")
async def authorize_proxy(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    scope: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: str = "S256",
):
    """Swap dynamic client_id for real Entra credentials and redirect to Entra."""
    # Always include the API scope so the token audience matches valid_audiences.
    # scope is optional — some clients (e.g. Copilot Studio) omit it.
    api_scope = f"api://{config.AZURE_CLIENT_ID}/access_as_user"
    scopes = set(scope.split()) if scope else set()
    scopes.add(api_scope)
    scopes.add("offline_access")
    merged_scope = " ".join(sorted(scopes))

    params: dict[str, str] = {
        "client_id": config.AZURE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": merged_scope,
        "state": state,
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = code_challenge_method

    entra_url = f"{_ENTRA_AUTHORIZE}?{urllib.parse.urlencode(params)}"
    logger.info(
        "authorize_proxy: client=%s scope=%s → Entra", client_id, merged_scope
    )
    return RedirectResponse(url=entra_url, status_code=302)


@router.post("/token")
async def token_proxy(request: Request):
    """Swap dynamic credentials for real Entra credentials and proxy token exchange."""
    form = await request.form()
    data = dict(form)

    dynamic_client_id = data.get("client_id", "")
    if not dynamic_client_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8", errors="replace")
            dynamic_client_id = decoded.split(":", 1)[0]

    logger.info(
        "token_proxy: client=%s grant_type=%s",
        dynamic_client_id,
        data.get("grant_type"),
    )

    data["client_id"] = config.AZURE_CLIENT_ID
    data.pop("resource", None)      # Entra v2 rejects RFC 8707 'resource' parameter
    if config.AZURE_CLIENT_SECRET:
        # Replace any incoming secret with the real one.
        data.pop("client_secret", None)
        data["client_secret"] = config.AZURE_CLIENT_SECRET
    # else: leave any incoming client_secret as-is so PKCE or client-provided
    # secrets pass through when AZURE_CLIENT_SECRET is not configured.

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                _ENTRA_TOKEN,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
    except httpx.TimeoutException:
        logger.error("token_proxy: httpx timeout calling Entra token endpoint")
        return JSONResponse(status_code=504, content={"error": "upstream_timeout", "message": "Entra token endpoint timed out"})
    except httpx.RequestError as exc:
        logger.error("token_proxy: httpx error calling Entra token endpoint: %s", exc)
        return JSONResponse(status_code=502, content={"error": "upstream_error", "message": str(exc)})

    if response.status_code != 200:
        logger.warning(
            "token_proxy: Entra returned %s — %s",
            response.status_code,
            response.text,
        )
        return JSONResponse(status_code=response.status_code, content=response.json())

    body = response.json()
    logger.info(
        "token_proxy: success token_type=%s expires_in=%s has_access_token=%s",
        body.get("token_type"),
        body.get("expires_in"),
        "access_token" in body,
    )
    return JSONResponse(status_code=200, content=body)
