## Purpose

Defines the local mock MCP Apps host that developers use to run and test an app's UI and its host protocol handling without a real MCP client.

## Requirements

### Requirement: Mock host runs an app against a real or simulated backend
The mock host SHALL serve a page that renders an app in a sandboxed iframe. In real mode it SHALL forward JSON-RPC calls to a configured MCP server using a configured API key; in mock mode it SHALL answer them locally without a server.

#### Scenario: Real mode
- **WHEN** the host is started with an MCP server URL and API key and opened without a mock parameter
- **THEN** it lists tools, calls the app tool, reads the app's `ui://` resource from the server and renders it

#### Scenario: Mock mode
- **WHEN** the page is opened with a mock scenario parameter
- **THEN** it renders the app with locally generated tool results and no server is contacted

### Requirement: Simulated scenarios for the example app
Mock mode SHALL support scenarios for a Bearer caller, an API-key caller, a permission-denied error, and a case where only the ping call is denied.

#### Scenario: Denied
- **WHEN** the page is opened with the denied scenario
- **THEN** the app tool result is an error with an authorization message and the app shows that message

#### Scenario: Only ping denied
- **WHEN** the page is opened with the ping-denied scenario and the user clicks the ping control
- **THEN** the app tool result is normal and the app shows the authorization message as the ping result

### Requirement: Host behaviors that apps must tolerate
The mock host SHALL support a dark theme, a narrow width, a mode in which it accepts only an array of content in a chat message, and a mode in which it rejects every chat message, selectable by URL parameters.

#### Scenario: Array-only host
- **WHEN** the page is opened with the array-only parameter and the app sends a single content object
- **THEN** the host rejects the message

#### Scenario: Chat rejected
- **WHEN** the page is opened with the reject-all parameter and the app sends a chat message in either format
- **THEN** the host rejects both attempts and records no accepted chat message

### Requirement: Host enforces tool visibility
The mock host SHALL reject an app-initiated tool call when the target tool's visibility does not include `app`.

#### Scenario: Model-only tool
- **WHEN** the app asks the host to call a tool whose visibility is only `model`
- **THEN** the host answers with an error and does not forward the call

### Requirement: Host records every message
The mock host SHALL record every message exchanged with the app, and every chat message the app sends, in page-level variables that automated tests can read.

#### Scenario: Inspecting the log
- **WHEN** an automated test reads the host log after interacting with the app
- **THEN** it contains the handshake, the tool calls and any chat message in order

### Requirement: Host can tear the app down
The mock host SHALL provide a control that sends a resource teardown request to the app.

#### Scenario: Teardown request
- **WHEN** the teardown control is used
- **THEN** the host sends the teardown request and records the app's reply
