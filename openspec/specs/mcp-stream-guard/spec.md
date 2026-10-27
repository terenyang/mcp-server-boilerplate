## Purpose

Defines how the service bounds MCP HTTP requests, by concurrency and time, without breaking long-lived notification streams or leaving clients with truncated responses.

## Requirements

### Requirement: Concurrent MCP requests are capped
The service SHALL allow at most the configured number of concurrent MCP requests and SHALL answer a request that cannot obtain a slot within the queue timeout with 429 and a `Retry-After` header.

#### Scenario: Cap exceeded
- **WHEN** the cap is reached and another request waits longer than the queue timeout
- **THEN** that request receives 429 with `Retry-After`

#### Scenario: Slot released
- **WHEN** a request finishes, successfully or by timeout
- **THEN** the active stream count decreases and a waiting request can proceed

### Requirement: Idle timeout applies to request/response calls only
The service SHALL end a non-GET MCP request that produces no response activity for longer than the idle timeout, and SHALL NOT apply the idle timeout to a `GET` request, which is the long-lived SSE notification stream.

#### Scenario: Idle POST
- **WHEN** a POST request sends no response data for longer than the idle timeout
- **THEN** the request is cancelled

#### Scenario: Idle GET stream
- **WHEN** a GET request has sent its response start and then stays silent for longer than the idle timeout
- **THEN** the stream stays open

### Requirement: Hard timeout applies to every request
The service SHALL cancel any MCP request, including a GET stream, that runs longer than the hard timeout.

#### Scenario: GET stream reaches the hard timeout
- **WHEN** a GET stream stays open past the hard timeout
- **THEN** the stream is closed

### Requirement: Timed-out responses terminate cleanly
When a timeout or cancellation ends a request whose response has started but not finished, the service SHALL complete the response with an empty final body. When the response had not started, the service SHALL return 503 with a JSON error.

#### Scenario: Cancelled mid-stream
- **WHEN** a request is cancelled after its response start was sent and before its final body
- **THEN** the client receives a final empty body with no further data expected

#### Scenario: Cancelled before any response
- **WHEN** a request is cancelled before it sent a response start
- **THEN** the client receives a 503 with error `mcp_stream_timeout`

### Requirement: Response start counts as activity
The service SHALL treat sending a response start as activity for the idle timer.

#### Scenario: Slow body after headers
- **WHEN** a POST request sends response headers just before the idle timeout would expire and the body follows within one idle period
- **THEN** the request is not cancelled
