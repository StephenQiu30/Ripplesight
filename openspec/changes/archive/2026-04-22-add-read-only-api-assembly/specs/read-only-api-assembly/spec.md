## ADDED Requirements

### Requirement: Assemble a FastAPI read-only service
The system SHALL provide a FastAPI service assembly that exposes the first read-only governance and hotspot routes without placing core business logic inside route handlers.

#### Scenario: Create the API application
- **WHEN** the API service module is loaded for startup or testing
- **THEN** it provides a FastAPI application with the configured read-only routers mounted

#### Scenario: Keep route handlers thin
- **WHEN** a request is handled by a read-only API endpoint
- **THEN** the route delegates business behavior to backend-core services and serializers instead of re-implementing domain logic

### Requirement: Expose governance endpoints with pagination-compatible responses
The system SHALL expose read-only governance endpoints for source configs, X keyword rules, and monitored X accounts using responses aligned with the current OpenAPI contract.

#### Scenario: List sources with enabled filtering
- **WHEN** a client requests `/api/sources`
- **THEN** the service returns a paginated source response and applies the optional `enabled` filter

#### Scenario: List X governance records
- **WHEN** a client requests `/api/x/keywords` or `/api/x/accounts`
- **THEN** the service returns read-only item lists with shared metadata structure

### Requirement: Expose hotspot event endpoints backed by the core services
The system SHALL expose read-only event list and detail endpoints using the backend-core hotspot discovery service and deterministic bootstrap data.

#### Scenario: List hotspot events
- **WHEN** a client requests `/api/events`
- **THEN** the service returns a paginated event list that supports the currently defined read filters

#### Scenario: Fetch a hotspot event by identifier
- **WHEN** a client requests `/api/events/{event_id}` for an existing event
- **THEN** the service returns the corresponding hotspot event detail payload

### Requirement: Provide automated API verification
The system SHALL include automated API tests for the first read-only service slice.

#### Scenario: Verify read-only route behavior
- **WHEN** the API test suite runs
- **THEN** it verifies the first read-only routes, including filtering and not-found handling
