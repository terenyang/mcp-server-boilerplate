"""API key validation."""
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
import config

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def ensure_valid_api_key(api_key: str) -> None:
    valid_keys = [k.strip() for k in config.API_KEYS.split(",") if k.strip()]
    if not valid_keys or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
