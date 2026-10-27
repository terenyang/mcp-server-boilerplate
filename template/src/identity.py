"""Caller identity data shared by tools and apps.

Lives outside src/server.py so the apps package can use it without importing the
server module (server.py imports the apps package; a back-import would be a cycle).
"""
from typing import Any, Dict

from src.auth_context import get_auth


def identity_info() -> Dict[str, Any]:
    """Describe the current caller from the request's auth context."""
    auth = get_auth()

    if auth is None or auth.auth_type == "api_key":
        return {
            "auth_type": "api_key",
            "message": "Authenticated via API key — no JWT token available.",
            "user": None,
        }

    return {
        "auth_type": "bearer",
        "user": {
            "oid": auth.user_oid,
            "name": auth.user_name,
            "upn": auth.user_upn,
        },
    }
