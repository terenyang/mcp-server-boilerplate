"""MCP App package: HTML loader, bridge inlining, whoami_card tool, HTML content."""
import re

import pytest
from mcp_types import CallToolResult

from src.apps import loader
from src.apps.loader import BRIDGE_PLACEHOLDER, load_app_html
from src.apps.whoami_card import CARD_HTML, whoami_card
from src.auth_context import AuthContext, set_auth


# --- loader and bridge -------------------------------------------------------

def test_load_app_html_inlines_bridge_and_removes_placeholder():
    html = load_app_html("whoami_card.html")

    assert BRIDGE_PLACEHOLDER not in html
    assert "__APP_BRIDGE__" not in html
    assert "window.McpApp" in html
    assert "ui/initialize" in html
    assert "ui/notifications/initialized" in html


def test_load_app_html_fails_loudly_without_placeholder(tmp_path, monkeypatch):
    (tmp_path / "app_bridge.js").write_text("// bridge", encoding="utf-8")
    (tmp_path / "broken.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(loader, "APPS_DIR", tmp_path)

    with pytest.raises(ValueError, match="placeholder"):
        load_app_html("broken.html")


def test_bridge_measures_body_not_document_element():
    html = load_app_html("whoami_card.html")

    assert "document.body.getBoundingClientRect()" in html
    # Mentions inside // comments are fine; code must not use it.
    assert not re.search(r"^[^/\n]*documentElement\.scrollHeight", html, re.M)


# --- whoami_card tool -------------------------------------------------------

@pytest.mark.asyncio
async def test_whoami_card_for_api_key_caller():
    set_auth(AuthContext(auth_type="api_key"))

    result = await whoami_card()

    assert isinstance(result, CallToolResult)
    assert "API key" in result.content[0].text
    assert result.structured_content["auth_type"] == "api_key"
    assert result.structured_content["user"] is None


@pytest.mark.asyncio
async def test_whoami_card_for_bearer_caller():
    set_auth(AuthContext(
        auth_type="bearer", user_oid="oid-1", user_name="Jane Doe", user_upn="jane@corp.com"
    ))

    result = await whoami_card()

    assert "Jane Doe" in result.content[0].text
    assert "jane@corp.com" in result.content[0].text
    assert result.structured_content["auth_type"] == "bearer"
    assert result.structured_content["user"] == {
        "oid": "oid-1", "name": "Jane Doe", "upn": "jane@corp.com"
    }


# --- HTML content -----------------------------------------------------------

def test_app_html_has_no_external_references():
    assert not re.search(r"<script[^>]+\bsrc\s*=", CARD_HTML, re.I)
    assert not re.search(r"<link\b", CARD_HTML, re.I)
    assert "@import" not in CARD_HTML
    assert not re.search(r"""(?:src|href)\s*=\s*["']https?:""", CARD_HTML, re.I)


def test_app_html_builds_dom_without_innerhtml():
    assert not re.search(r"\.innerHTML\s*\+?=", CARD_HTML)


# --- registry ---------------------------------------------------------------

def test_package_exports_the_shared_registry():
    # Registration itself is covered by the wire tests (tool and resource are listed).
    import src.apps as package
    from src.apps.registry import apps

    assert package.apps is apps


def test_whoami_card_module_does_not_define_its_own_registry():
    from src.apps import whoami_card as module
    from src.apps.registry import apps

    assert module.apps is apps
