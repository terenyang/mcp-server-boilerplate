## Purpose

Defines how tool failures, especially authorization failures raised before a tool body runs, are reported to MCP clients so that users and models see an actionable message.

## Requirements

### Requirement: Tool failure messages reach the client
When a guarded tool fails for any reason, the service SHALL return a tool result with `isError` set to true whose text contains the failure's own message, not a generic "Error executing tool" text.

#### Scenario: User has no groups in token
- **WHEN** `ALLOWED_ENTRA_GROUPS` is configured and a caller without group claims invokes a guarded tool
- **THEN** the result has `isError` true and its text contains "No Entra groups found in token"

#### Scenario: User not in an allowed group
- **WHEN** `ALLOWED_ENTRA_GROUPS` is configured and the caller's groups do not intersect it
- **THEN** the result has `isError` true and its text contains "User is not authorized to access this tool"

#### Scenario: Unexpected exception inside a tool body
- **WHEN** a guarded tool body raises an exception with a message
- **THEN** the result has `isError` true and its text contains that message

### Requirement: Failures are logged with diagnostics
The service SHALL log each guarded tool failure with the tool name and a traceback, because the client-facing result carries only the message.

#### Scenario: Failure is logged
- **WHEN** a guarded tool fails
- **THEN** a warning-level log entry naming the tool and including the traceback is emitted

### Requirement: All built-in tools honor group restriction
Every built-in tool (`whoami`, `ping`) that is subject to `ALLOWED_ENTRA_GROUPS` SHALL apply the same group check before executing.

#### Scenario: ping in restricted mode
- **WHEN** `ALLOWED_ENTRA_GROUPS` is configured and a caller without a permitted group invokes `ping`
- **THEN** the result has `isError` true and the tool body does not run

### Requirement: Group restriction evaluates the caller's token claims
When `ALLOWED_ENTRA_GROUPS` is configured, the service SHALL decide access for an Entra Bearer caller from the `groups` claim of that caller's validated token.

#### Scenario: Bearer user in an allowed group
- **WHEN** `ALLOWED_ENTRA_GROUPS` is configured and a Bearer caller's token `groups` claim contains a permitted group
- **THEN** the guarded tool executes and returns its normal result

#### Scenario: Bearer user not in an allowed group
- **WHEN** `ALLOWED_ENTRA_GROUPS` is configured and a Bearer caller's token `groups` claim contains no permitted group
- **THEN** the result has `isError` true and its text contains "User is not authorized to access this tool"

#### Scenario: Bearer token without groups claim
- **WHEN** `ALLOWED_ENTRA_GROUPS` is configured and a Bearer caller's token has no `groups` claim
- **THEN** the result has `isError` true and its text contains "No Entra groups found in token"

### Requirement: Argument validation errors remain visible
The service SHALL continue to return argument validation failures with their full text.

#### Scenario: Wrong argument type
- **WHEN** a client calls `ping` with a non-string `message`
- **THEN** the result is an error whose text describes the validation failure
