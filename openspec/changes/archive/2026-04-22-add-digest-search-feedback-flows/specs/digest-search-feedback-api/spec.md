## ADDED Requirements

### Requirement: Expose today's digest from the assembled service
The system SHALL expose a read-only API endpoint that returns the current daily digest derived from the available hotspot event set.

#### Scenario: Retrieve today's digest
- **WHEN** a client requests `/api/digests/today`
- **THEN** the service returns the assembled digest payload for the current day

#### Scenario: Build digest highlights from hotspot events
- **WHEN** the digest is assembled for API output
- **THEN** it includes highlights and event references derived from the current ranked hotspot events

### Requirement: Expose hotspot search over the available event set
The system SHALL expose a search endpoint that queries hotspot events using the provided search string.

#### Scenario: Search hotspot events
- **WHEN** a client requests `/api/search` with a non-empty query
- **THEN** the service returns matching hotspot events in the shared paginated response structure

#### Scenario: Search across event summaries and titles
- **WHEN** the search workflow runs
- **THEN** it evaluates matches against the current event title and summary fields

### Requirement: Accept feedback submissions through the API
The system SHALL expose a feedback submission endpoint for events and digests.

#### Scenario: Submit feedback
- **WHEN** a client posts a valid feedback record to `/api/feedback`
- **THEN** the service persists the feedback record and returns it with a `201` response

#### Scenario: Stamp new feedback records
- **WHEN** feedback is accepted
- **THEN** the system assigns an identifier and creation timestamp before returning the saved record

### Requirement: Verify digest, search, and feedback behavior automatically
The system SHALL include automated tests for the digest, search, and feedback endpoints.

#### Scenario: Run API verification
- **WHEN** the API test suite runs
- **THEN** it verifies digest retrieval, search matching, and feedback submission behavior
