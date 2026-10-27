"""Read an app's HTML and inline the shared host bridge into it."""
from pathlib import Path

APPS_DIR = Path(__file__).parent
BRIDGE_PLACEHOLDER = "/*__APP_BRIDGE__*/"


def load_app_html(name: str) -> str:
    """Return apps/<name> with app_bridge.js inlined at the bridge placeholder.

    Read once at import time, so edits to the HTML or JS need a server restart
    (uvicorn --reload watches only .py files).
    """
    html = (APPS_DIR / name).read_text(encoding="utf-8")
    if BRIDGE_PLACEHOLDER not in html:
        raise ValueError(f"{name} does not contain the {BRIDGE_PLACEHOLDER} placeholder")
    bridge = (APPS_DIR / "app_bridge.js").read_text(encoding="utf-8")
    return html.replace(BRIDGE_PLACEHOLDER, bridge, 1)
