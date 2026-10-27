"""Local mock MCP Apps host for testing ui:// resources (dev only).

Run from the template directory so the project's dependencies are available:

    uv run python scripts/mcp_app_host/serve.py [--port 8765] [--mcp http://127.0.0.1:8080]

Real mode proxies JSON-RPC to a running MCP server (API key from MCP_API_KEY):
    http://127.0.0.1:8765/
Mock mode needs no server; scenarios are bearer, apikey, denied (the app tool
fails) and pingdenied (the card loads, only ping fails):
    http://127.0.0.1:8765/?mock=bearer
Other URL parameters: theme=dark, width=360, msgArray=1 (host accepts only an
array of chat-message content), tool=<app tool name>.

Binds to 127.0.0.1 only. This is a development tool, not a production host.
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))  # template root, for src.apps


def _app_html() -> str:
    # Mock mode serves the app straight from the source tree, bridge inlined.
    from src.apps.loader import load_app_html

    return load_app_html("whoami_card.html")


def _first_rpc_message(response: httpx.Response):
    """Return the JSON-RPC response from a JSON or SSE reply."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                message = json.loads(line[5:])
                if "id" in message:
                    return message
        return None
    return response.json()


def make_handler(mcp_url: str, api_key: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body, content_type: str):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                return self._send(200, (HERE / "host.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if path == "/app.html":
                return self._send(200, _app_html(), "text/plain; charset=utf-8")
            self._send(404, "not found", "text/plain")

        def do_POST(self):
            if self.path.split("?")[0] != "/rpc":
                return self._send(404, "not found", "text/plain")
            body = self.rfile.read(int(self.headers["content-length"]))
            try:
                r = httpx.post(
                    mcp_url,
                    content=body,
                    timeout=320,
                    headers={
                        "content-type": "application/json",
                        "accept": "application/json, text/event-stream",
                        "mcp-protocol-version": "2025-06-18",
                        "x-api-key": api_key,
                    },
                )
                message = _first_rpc_message(r) or {"error": {"message": f"HTTP {r.status_code}"}}
            except httpx.HTTPError as exc:
                message = {"error": {"message": f"Cannot reach the MCP server: {exc}"}}
            self._send(200, json.dumps(message), "application/json")

    return Handler


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mcp", default="http://127.0.0.1:8080")
    args = ap.parse_args()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(args.mcp.rstrip("/") + "/mcp/", os.environ.get("MCP_API_KEY", "")),
    )
    print(f"Mock MCP Apps host on http://127.0.0.1:{args.port}/  (MCP server: {args.mcp})")
    server.serve_forever()
