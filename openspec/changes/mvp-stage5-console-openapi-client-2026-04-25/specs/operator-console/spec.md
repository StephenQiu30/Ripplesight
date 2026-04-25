## MODIFIED Requirements

### Requirement: Browse today's hotspot ranking
The system SHALL provide an operator console view for browsing the current hotspot ranking through generated OpenAPI client services, with paginated list and filter support.

#### Scenario: View today's hotspot list
- **WHEN** an internal user opens the hotspot ranking view
- **THEN** the system returns the paginated event list for the current ranked hotspot set
- **AND** the list uses data from the generated OpenAPI client bindings of `GET /api/events`.

#### Scenario: Filter hotspot list by topic or source type
- **WHEN** an internal user applies supported topic or source filters
- **THEN** the system returns the filtered hotspot list using the shared pagination structure
- **AND** invalid filter combinations return a graceful empty list or a user-visible error message.

### Requirement: Inspect hotspot event details and source trace
The system SHALL provide a detail view for each hotspot event with event summary, source count, and traceable evidence links.

#### Scenario: Open event details
- **WHEN** an internal user requests a specific hotspot event
- **THEN** the system returns the event detail payload for that event identifier
- **AND** the detail view is rendered with fallback content on not-found.

#### Scenario: Review source trace
- **WHEN** the event detail view is displayed
- **THEN** the system exposes the source evidence chain needed to inspect where the event came from
- **AND** the evidence rendering uses the event payload from `GET /api/events/{event_id}` generated client output.

### Requirement: Search and filter recent hotspot history
The system SHALL support keyword search and time-based filtering across hotspot events and related summaries with OpenAPI client-backed requests.

#### Scenario: Search by keyword
- **WHEN** an internal user submits a search query
- **THEN** the system returns matching hotspot events in a paginated search response
- **AND** query requests use `GET /api/search` generated client bindings.

#### Scenario: Filter by date window
- **WHEN** an internal user requests a date-bounded event view
- **THEN** the system limits the returned hotspot events to the requested date range
- **AND** empty windows return a consistent empty state.

### Requirement: Capture operator feedback
The system SHALL allow internal users to submit feedback on events or digests for later relevance tuning and quality improvement through generated typed request payloads.

#### Scenario: Submit event feedback
- **WHEN** an internal user submits feedback for a hotspot event
- **THEN** the system records the feedback with the target type, target identifier, feedback type, and creation time
- **AND** success and failure states are surfaced on submit action.

#### Scenario: Use feedback as an optimization input
- **WHEN** feedback records are stored
- **THEN** the system preserves them for future weighting, tuning, or quality-review workflows
- **AND** the request payload conforms to the shared OpenAPI schema.

## ADDED Requirements

### Requirement: Browse source governance configuration read-only
The system SHALL provide read-only console views for sources, monitored X keywords, and monitored X accounts based on existing APIs.

#### Scenario: List source configs
- **WHEN** an operator opens the Source Config page
- **THEN** the system requests `/api/sources` and displays configured sources with enabled state and metadata.

#### Scenario: List X rules
- **WHEN** an operator opens the X rules page
- **THEN** the system requests `/api/x/keywords` and `/api/x/accounts` and displays the configured rule/account lists.
