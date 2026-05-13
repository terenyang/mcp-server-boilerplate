"""Configuration from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
API_KEYS = os.getenv("API_KEYS", "")

SERVICE_NAME = os.getenv("SERVICE_NAME", "MCP Boilerplate")
SERVICE_OWNER = os.getenv("SERVICE_OWNER", "Your Org")

AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

# Stream concurrency (optional tuning)
MAX_CONCURRENT_STREAMS = int(os.getenv("MAX_CONCURRENT_STREAMS", "20"))
QUEUE_WAIT_TIMEOUT = int(os.getenv("QUEUE_WAIT_TIMEOUT", "5"))
HARD_STREAM_TIMEOUT = int(os.getenv("HARD_STREAM_TIMEOUT", "300"))
IDLE_STREAM_TIMEOUT = int(os.getenv("IDLE_STREAM_TIMEOUT", "60"))
