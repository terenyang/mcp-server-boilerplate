"""whoami_card: example MCP App showing the signed-in identity.

The UI (whoami_card.html) runs in a host-rendered iframe. It renders the tool
result's structured content, and calls `ping` through the host's tools/call, so
permissions are enforced exactly as for model-initiated calls.
"""
from mcp.server.apps import ResourcePermissions
from mcp_types import CallToolResult, TextContent

from src.apps.loader import load_app_html
from src.apps.registry import apps
from src.deps import check_entra_groups, tool_guard
from src.identity import identity_info

CARD_URI = "ui://boilerplate/whoami-card.html"
# Display name; hosts otherwise derive "Whoami card" from the tool name
CARD_TITLE = "Who Am I"
CARD_HTML = load_app_html("whoami_card.html")

apps.add_html_resource(
    CARD_URI,
    CARD_HTML,
    name=CARD_TITLE,
    description="Interactive card showing who is signed in, with a ping check.",
    permissions=ResourcePermissions(clipboard_write={}),
    prefers_border=True,  # the spec recommends stating this explicitly
)


# "ui/resourceUri" is the legacy flat key older hosts read; the ext-apps SDK sets both.
# Decorator order: @apps.tool outside, @tool_guard inside (same as @mcp.tool()).
@apps.tool(resource_uri=CARD_URI, meta={"ui/resourceUri": CARD_URI}, title=CARD_TITLE)
@tool_guard(depends_on=[check_entra_groups])
async def whoami_card() -> CallToolResult:
    """Show who is signed in as an interactive card.

    Clients that cannot display MCP Apps get the same information as text; the
    `whoami` tool returns it as JSON.
    """
    info = identity_info()
    user = info["user"]
    if user:
        text = (
            f"Signed in as {user.get('name') or 'unknown'} ({user.get('upn') or 'no UPN'}) "
            "via Entra ID (bearer token)."
        )
    else:
        text = "Authenticated via API key — no user token is present."
    # Always return text and structured content: client_supports_apps() is not
    # reliable in stateless mode, so the format cannot depend on the client.
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=info,
    )
