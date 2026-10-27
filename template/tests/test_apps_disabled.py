"""ENABLE_MCP_APPS is read at import and extensions are fixed when MCPServer is
constructed, so the disabled configuration can only be checked in a fresh process."""
import json
import os
import subprocess
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[1]
BASELINE = Path(__file__).parent / "fixtures" / "tools_list_baseline.json"

SCRIPT = r"""
import json
from fastapi.testclient import TestClient
from main import app

H = {"x-api-key": "k", "content-type": "application/json",
     "accept": "application/json, text/event-stream"}

def rpc(client, method, params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    r = client.post("/mcp", headers=H, json=body)
    for line in r.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:])
    return r.json()

with TestClient(app) as client:
    out = {
        "tools": rpc(client, "tools/list")["result"]["tools"],
        "resources": rpc(client, "resources/list")["result"]["resources"],
    }
print("RESULT:" + json.dumps(out))
"""


def _server_listing(enable_apps: str) -> dict:
    env = {**os.environ, "ENABLE_MCP_APPS": enable_apps, "API_KEYS": "k", "PYTHONPATH": str(TEMPLATE_DIR)}
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=TEMPLATE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(l for l in proc.stdout.splitlines() if l.startswith("RESULT:"))
    return json.loads(line[len("RESULT:"):])


def test_disabled_apps_list_exactly_the_pre_app_server():
    listing = _server_listing("false")

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["result"]["tools"]
    key = lambda t: t["name"]
    assert sorted(listing["tools"], key=key) == sorted(baseline, key=key)
    assert not any(r["uri"].startswith("ui://") for r in listing["resources"])


def test_enabled_apps_differ_so_the_disabled_check_is_not_vacuous():
    listing = _server_listing("true")

    assert "whoami_card" in {t["name"] for t in listing["tools"]}
    assert any(r["uri"].startswith("ui://") for r in listing["resources"])
