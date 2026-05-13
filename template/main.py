"""ASGI entry point — thin wrapper so uvicorn uses `main:app`."""
from src.http.app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
