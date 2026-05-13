# Contributing

Thanks for improving this MCP server boilerplate.

## Local Setup

```bash
cd template
uv sync --extra dev
cp .env.example .env
uv run pytest
```

## Pull Request Checklist

- Keep template changes small and reusable.
- Add or update tests for behavior changes.
- Update the README or docs when setup steps change.
- Do not commit secrets, tokens, `.env`, or generated virtual environments.

## Design Principles

- Prefer readable code over clever abstractions.
- Keep authentication and transport concerns isolated from tool logic.
- Make defaults useful for local development and explicit for production.
- Document client-specific workarounds when they affect real integrations.
