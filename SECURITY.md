# Security Policy

This project is a boilerplate for authenticated MCP servers. Treat every fork as a real service before exposing it publicly.

## Baseline Recommendations

- Rotate `API_KEYS` before deploying.
- Use HTTPS for any non-local `BASE_URL`.
- Restrict CORS origins before production use.
- Store Azure secrets in a secret manager, not in source control.
- Review OAuth redirect URIs and remove development callbacks when no longer needed.
- Monitor `/health` and application logs after enabling public access.

## Reporting Issues

If you find a security issue in this boilerplate, please open a private advisory or contact the maintainer directly. Avoid posting working exploits in public issues.
