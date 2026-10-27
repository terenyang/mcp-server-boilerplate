## Purpose

Defines how the template exposes its MCP endpoint over HTTP so that desktop, web and tunnelled clients can connect without redirects, host rejections or session state.

## ADDED Requirements

### Requirement: MCP endpoint served at both /mcp and /mcp/
The service SHALL serve the MCP streamable-HTTP endpoint at `/mcp` and `/mcp/` with identical behavior, and SHALL NOT answer either with a redirect or a 404.

#### Scenario: Initialize without trailing slash
- **WHEN** an authenticated client sends a `POST /mcp` JSON-RPC `initialize` request
- **THEN** the response status is 200 and the body is a valid `initialize` result

#### Scenario: Initialize with trailing slash
- **WHEN** an authenticated client sends a `POST /mcp/` JSON-RPC `initialize` request
- **THEN** the response status is 200 and the body is a valid `initialize` result

#### Scenario: No doubled path
- **WHEN** a client sends a request to `/mcp/mcp`
- **THEN** the service does not treat it as the MCP endpoint

### Requirement: Requests from non-localhost hosts are accepted
The service SHALL NOT reject MCP requests based on the `Host` or `Origin` header, so that it can run behind tunnels, gateways and public domains. Authentication remains the access control.

#### Scenario: Public host header
- **WHEN** an authenticated client sends an MCP request with `Host: example.devtunnels.ms`
- **THEN** the request is processed and is not rejected with 421 or 403

### Requirement: MCP transport is stateless
The service SHALL handle each MCP HTTP request independently, without requiring a session identifier from a prior `initialize`.

#### Scenario: Tool call without prior initialize
- **WHEN** an authenticated client sends `tools/call` for an existing tool in a request that has no session header
- **THEN** the call is executed and its result is returned

### Requirement: Registered tools are listed
The service SHALL list every registered tool through `tools/list`, with names, descriptions and input schemas.

#### Scenario: Default tool set
- **WHEN** an authenticated client sends `tools/list`
- **THEN** the result contains `whoami`, `ping` and `server_profile`, each with an input schema
