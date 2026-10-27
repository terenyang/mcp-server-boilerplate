"""Configuration from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


def _env_flag(name: str, default: str = "true") -> bool:
    """Read a boolean env var: "false", "0" and "no" (any case) are off."""
    return os.getenv(name, default).strip().lower() not in ("false", "0", "no")


BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
API_KEYS = os.getenv("API_KEYS", "")

SERVICE_NAME = os.getenv("SERVICE_NAME", "MCP Boilerplate")
SERVICE_OWNER = os.getenv("SERVICE_OWNER", "Your Org")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")

AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
REQUIRED_SCOPE = os.getenv("REQUIRED_SCOPE", "MCP.Access")

# Tool authorization / audit configuration
AUTH_METHOD = os.getenv("AUTH_METHOD", "entra_auth")
ALLOWED_ENTRA_GROUPS = {
    group_id.strip()
    for group_id in os.getenv("ALLOWED_ENTRA_GROUPS", "").split(",")
    if group_id.strip()
}

# Stream concurrency (optional tuning)
MAX_CONCURRENT_STREAMS = int(os.getenv("MAX_CONCURRENT_STREAMS", "20"))
QUEUE_WAIT_TIMEOUT = int(os.getenv("QUEUE_WAIT_TIMEOUT", "5"))
HARD_STREAM_TIMEOUT = int(os.getenv("HARD_STREAM_TIMEOUT", "300"))
IDLE_STREAM_TIMEOUT = int(os.getenv("IDLE_STREAM_TIMEOUT", "60"))

# MCP Apps (interactive UI). Set to "false" to hide app tools/resources from
# clients that mishandle them.
ENABLE_MCP_APPS = _env_flag("ENABLE_MCP_APPS")
