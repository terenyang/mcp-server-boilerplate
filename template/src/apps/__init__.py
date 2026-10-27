"""MCP Apps (io.modelcontextprotocol/ui) registered on the MCP server.

`apps` must be fully populated before MCPServer is constructed: mcp 2.x fixes
extensions at construction time and silently ignores anything registered later.
That is why apps live in this package and src/server.py only imports it.
"""
import config
from src.apps.loader import load_app_html
from src.apps.registry import apps

# Importing an app module registers its tool and resource on `apps`. Add new app
# modules here; this package is imported before MCPServer is constructed.
from src.apps import whoami_card  # noqa: F401

# _meta for tools an app calls through the host. Hosts reject an app-initiated
# tools/call unless the tool's visibility includes "app"; the spec leaves tools
# without _meta.ui undefined, so state it explicitly, and only for the tools an
# app actually needs (app calls run with the user's token).
APP_CALLABLE_META = {"ui": {"visibility": ["model", "app"]}} if config.ENABLE_MCP_APPS else None

__all__ = ["apps", "APP_CALLABLE_META", "load_app_html"]
