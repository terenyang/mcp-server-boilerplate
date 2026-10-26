## Purpose

Defines the OAuth discovery documents, challenge responses and the Entra proxy endpoints that let MCP clients that require dynamic client registration authenticate against Azure Entra.

## ADDED Requirements

### Requirement: Protected-resource metadata at bare and path-suffixed URLs
The service SHALL serve the same OAuth protected-resource metadata document at `/.well-known/oauth-protected-resource` and at `/.well-known/oauth-protected-resource/mcp`, without authentication. The document's `resource` SHALL be the MCP endpoint URL and its `authorization_servers` SHALL list this service, not Entra.

#### Scenario: Bare metadata URL
- **WHEN** a client requests `GET /.well-known/oauth-protected-resource`
- **THEN** the response is 200 and `resource` ends with `/mcp`

#### Scenario: Path-suffixed metadata URL
- **WHEN** a client requests `GET /.well-known/oauth-protected-resource/mcp`
- **THEN** the response is 200 with the same JSON document as the bare URL

### Requirement: Unauthenticated MCP requests are challenged with the path-suffixed metadata URL
The service SHALL answer an MCP request that carries no credentials with 401 and a `WWW-Authenticate` header of the form `Bearer resource_metadata="<BASE_URL>/.well-known/oauth-protected-resource/mcp"`.

#### Scenario: No token
- **WHEN** a client sends `POST /mcp/` without credentials
- **THEN** the response is 401 and the `WWW-Authenticate` header carries that `resource_metadata` URL

### Requirement: Dynamic client registration echoes requested grant types
The service SHALL accept a dynamic client registration request and return a client identifier and secret, echoing the requested `grant_types` and defaulting to `["authorization_code"]` when none are requested.

#### Scenario: Client requests several grant types
- **WHEN** a client registers with `grant_types` of `["authorization_code", "refresh_token"]`
- **THEN** the 201 response contains the same `grant_types`

#### Scenario: Client requests none
- **WHEN** a client registers without `grant_types`
- **THEN** the 201 response contains `grant_types` of `["authorization_code"]`

### Requirement: Authorize proxy works without state
The service SHALL redirect an authorization request to Entra whether or not the client supplied `state`, and SHALL NOT reject a request for lacking it.

#### Scenario: State omitted
- **WHEN** a client calls `GET /authorize` with `response_type`, `client_id` and `redirect_uri` but no `state`
- **THEN** the response is a 302 redirect to Entra's authorize endpoint

#### Scenario: State supplied
- **WHEN** a client calls `GET /authorize` with a `state` value
- **THEN** the redirect to Entra carries that same `state`

### Requirement: Authorize proxy normalizes scopes
The service SHALL send Entra exactly one form of the API scope, the full `api://<client id>/<required scope>`, together with `offline_access`, and SHALL preserve other scopes the client requested.

#### Scenario: Client sends the short scope name
- **WHEN** a client requests scopes that include the short required scope name and `openid`
- **THEN** the redirect to Entra contains the full API scope once, does not contain the short name, and still contains `openid` and `offline_access`

### Requirement: Token response identifies the MCP resource
The service SHALL add `resource`, equal to the MCP endpoint URL, to a successful token response that contains an access token.

#### Scenario: Successful code exchange
- **WHEN** Entra returns a token response with an `access_token` through the token proxy
- **THEN** the response to the client contains `resource` equal to `<BASE_URL>/mcp`

#### Scenario: Entra returns an error
- **WHEN** Entra returns a non-200 response
- **THEN** the service returns the same status and body without adding `resource`
