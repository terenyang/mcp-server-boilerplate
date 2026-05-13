"""Azure AD / Entra ID JWT token verification.

Validates bearer tokens as the OAuth 2.1 resource server role.
Per MCP spec, the server MUST validate that tokens were issued specifically
for it (audience check per RFC 8707 §2).

Accepted audiences:
  - api://{AZURE_CLIENT_ID}     (Azure AD App ID URI)
  - {AZURE_CLIENT_ID}           (raw client ID GUID)
  - {BASE_URL}                  (canonical MCP server URI per RFC 8707)
"""
import base64
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import jwt
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from fastapi import HTTPException

import config

logger = logging.getLogger(__name__)

valid_audiences = [
    f"api://{config.AZURE_CLIENT_ID}",
    config.AZURE_CLIENT_ID,
    config.BASE_URL.rstrip("/"),
]

# Accept both v2 (user tokens) and v1 (app/client-credentials tokens)
valid_issuers = [
    f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}/v2.0",
    f"https://sts.windows.net/{config.AZURE_TENANT_ID}/",
]

# In-memory JWKS cache (1-hour TTL)
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_expiry: Optional[datetime] = None
_JWKS_CACHE_DURATION = timedelta(hours=1)


class InvalidAuthorizationToken(Exception):
    def __init__(self, details: str):
        super().__init__("Invalid authorization token: " + details)


def _decode_value(val: Any) -> int:
    decoded = base64.urlsafe_b64decode(
        (val if isinstance(val, bytes) else val.encode()) + b"=="
    )
    return int.from_bytes(decoded, "big")


def _rsa_pem_from_jwk(jwk: Dict[str, Any]) -> bytes:
    return (
        RSAPublicNumbers(n=_decode_value(jwk["n"]), e=_decode_value(jwk["e"]))
        .public_key(default_backend())
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def _fetch_jwks() -> Optional[Dict[str, Any]]:
    global _jwks_cache, _jwks_cache_expiry

    if _jwks_cache and _jwks_cache_expiry and datetime.now() < _jwks_cache_expiry:
        return _jwks_cache

    try:
        url = f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}/discovery/v2.0/keys"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_expiry = datetime.now() + _JWKS_CACHE_DURATION
        return _jwks_cache
    except Exception as e:
        logger.error("Failed to fetch JWKS: %s", e)
        return _jwks_cache or None


def _get_public_key(token: str) -> bytes:
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    if not kid:
        raise InvalidAuthorizationToken("missing kid header")

    jwks = _fetch_jwks()
    if not jwks or "keys" not in jwks:
        raise InvalidAuthorizationToken("JWKS unavailable")

    for jwk in jwks["keys"]:
        if jwk.get("kid") == kid:
            return _rsa_pem_from_jwk(jwk)

    raise InvalidAuthorizationToken(f"Key ID {kid} not found in JWKS")


async def authenticate(token: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Validate an Azure AD JWT. Returns (user_oid, user_name, user_upn)."""
    if not config.AZURE_CLIENT_ID or not config.AZURE_TENANT_ID:
        raise HTTPException(
            status_code=500, detail="OAuth2 not configured on this server"
        )

    try:
        public_key = _get_public_key(token)

        unverified = jwt.decode(token, options={"verify_signature": False})
        logger.info(
            "jwt: aud=%s iss=%s scp=%s appid=%s",
            unverified.get("aud"),
            unverified.get("iss"),
            unverified.get("scp"),
            unverified.get("appid"),
        )

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=valid_audiences,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": False},
        )

        token_issuer = payload.get("iss", "")
        if token_issuer not in valid_issuers:
            logger.warning("Untrusted issuer: %s", token_issuer)
            raise jwt.InvalidIssuerError(f"Issuer not trusted: {token_issuer}")

        user_oid = payload.get("oid")
        if not user_oid:
            raise HTTPException(status_code=401, detail="Token missing 'oid' claim")

        return user_oid, payload.get("name"), payload.get("upn")

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=403, detail="Token not issued for this resource")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=403, detail="Token issuer not trusted")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except InvalidAuthorizationToken as e:
        raise HTTPException(status_code=401, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected auth error: %s", e)
        raise HTTPException(status_code=500, detail="Authentication failed")
