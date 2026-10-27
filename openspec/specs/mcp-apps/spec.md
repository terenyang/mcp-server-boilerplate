## Purpose

Defines how the service exposes MCP Apps: an example interactive card, the setting that turns apps on or off, which tools an app may call, and the plain-text behavior for clients that cannot display the UI.

## Requirements

### Requirement: Example app tool and UI resource
When apps are enabled, the service SHALL expose a tool named `whoami_card` and an HTML resource whose URI starts with `ui://`, and the tool SHALL reference that resource in its `_meta.ui.resourceUri`.

#### Scenario: Tool is listed with its resource
- **WHEN** an authenticated client sends `tools/list` with apps enabled
- **THEN** the result contains `whoami_card` whose metadata names a `ui://` resource URI

#### Scenario: Resource is readable as an app
- **WHEN** an authenticated client sends `resources/read` for that URI
- **THEN** the result has MIME type `text/html;profile=mcp-app` and a complete HTML document

### Requirement: App tool returns text and structured data
`whoami_card` SHALL return both human-readable text content and structured content describing the caller, and SHALL do so regardless of whether the client advertised UI support.

#### Scenario: Bearer caller
- **WHEN** a Bearer-authenticated caller invokes `whoami_card`
- **THEN** the result's text names the signed-in user and the structured content contains the user's identity and the auth type

#### Scenario: API-key caller
- **WHEN** an API-key caller invokes `whoami_card`
- **THEN** the text states that no user token is present and the structured content reports the auth type `api_key` with no user

### Requirement: App tool honors the same authorization as other tools
`whoami_card` SHALL apply the same group restriction and error reporting as the other guarded tools.

#### Scenario: Restricted mode denies the caller
- **WHEN** `ALLOWED_ENTRA_GROUPS` is configured and the caller lacks a permitted group
- **THEN** `whoami_card` returns `isError` true with the same authorization message as `whoami`

### Requirement: Apps can be disabled
The service SHALL read an `ENABLE_MCP_APPS` setting that defaults to enabled and treats `false`, `0` and `no` (any case) as disabled. When disabled, the service SHALL list the same tools, with the same metadata, as it did before apps existed, and SHALL list no `ui://` resources.

#### Scenario: Disabled
- **WHEN** the service starts with `ENABLE_MCP_APPS=false`
- **THEN** `tools/list` contains only `whoami`, `ping` and `server_profile`, none carrying `_meta.ui`, and `resources/list` has no `ui://` entries

#### Scenario: Default
- **WHEN** the service starts without `ENABLE_MCP_APPS`
- **THEN** apps are enabled

### Requirement: Only designated tools are callable by the app
Tools the example app calls SHALL declare `_meta.ui.visibility` including `app`; tools that do not need to be app-callable SHALL NOT be given that declaration by default.

#### Scenario: ping is app-callable
- **WHEN** apps are enabled and a client lists tools
- **THEN** `ping` declares visibility containing both `model` and `app`

#### Scenario: Other tools stay model-only by default
- **WHEN** apps are enabled
- **THEN** `whoami` and `server_profile` do not declare app visibility

### Requirement: The HTML app is self-contained
The app's HTML SHALL NOT reference any external script, stylesheet, font or import, and SHALL contain the host bridge inline.

#### Scenario: No external references
- **WHEN** the app HTML served by `resources/read` is searched for `http:` or `https:` script sources, stylesheet links and `@import`
- **THEN** none are found

#### Scenario: Bridge is inlined
- **WHEN** the app HTML is served
- **THEN** it does not contain the bridge placeholder and does contain the bridge code

### Requirement: App behavior in the host
The app SHALL complete the host handshake before rendering, SHALL report its content size to the host and shrink it when content shrinks, SHALL stop timers and answer when the host tears the resource down, and SHALL send a message to the chat only when the user clicks a control for it.

#### Scenario: Handshake and render
- **WHEN** the host initializes the app and delivers a tool result
- **THEN** the app shows the identity from the structured content

#### Scenario: Size follows content
- **WHEN** the displayed content becomes shorter
- **THEN** the app reports a smaller height to the host

#### Scenario: Calling ping through the host
- **WHEN** the user clicks the ping control
- **THEN** the app calls `ping` through the host and shows the returned text, or the error text if the call fails

#### Scenario: Send to chat is user-initiated
- **WHEN** the app has loaded and the user has not clicked the send control
- **THEN** the app has sent no chat message

#### Scenario: Host that only accepts a content array
- **WHEN** the user clicks send and the host rejects a single content object
- **THEN** the app retries once with the content as an array, and if that also fails shows the error and a copyable text of the message

#### Scenario: Teardown
- **WHEN** the host sends a resource teardown request
- **THEN** the app answers with an empty result and runs no further timers

### Requirement: Clients without UI get usable text
The text returned by `whoami_card` SHALL be sufficient on its own for a client that cannot display apps.

#### Scenario: Text-only client
- **WHEN** a client that ignores the UI resource invokes `whoami_card`
- **THEN** the text content alone tells the user who is signed in and how they authenticated
