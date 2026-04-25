## ADDED Requirements

### Requirement: Guarantee today's ranking visibility in console
The system SHALL provide a stable ranked list for current-day hotspots as a first-class console read path.

#### Scenario: Query today's ranking list
- **WHEN** an internal user opens the hotspot console for today
- **THEN** the system returns ranked events with event id, title, score, source count, and summary snippet

#### Scenario: Show ranking stability within a schedule window
- **WHEN** multiple requests are sent in the same day window
- **THEN** the ranking list remains consistent with the latest generated digest baseline

## MODIFIED Requirements

### Requirement: Browse today's hotspot ranking
The system SHALL provide an operator console view for browsing the current hotspot ranking.

#### Scenario: View today's hotspot list
- **WHEN** an internal user requests the hotspot ranking view
- **THEN** the system returns the paginated event list for the current ranked hotspot set

#### Scenario: Filter list by topic or source type
- **WHEN** filters are applied
- **THEN** the system returns the filtered list without breaking ranking metadata

### Requirement: Inspect hotspot event details and source trace
The system SHALL provide a detail view for each hotspot event with event summary, source count, and traceable evidence links.

#### Scenario: Open event details
- **WHEN** an internal user requests an event id
- **THEN** the system returns event details and evidence links for inspection

#### Scenario: Review full source trace
- **WHEN** source trace is displayed in detail view
- **THEN** the system exposes all contributing source items and their timestamps

### Requirement: Search and filter recent hotspot history
The system SHALL support keyword search and time-based filtering across hotspot events and related summaries.

#### Scenario: Search by keyword
- **WHEN** an internal user submits a search query
- **THEN** the system returns matching hotspot events with paginated response and source metadata

#### Scenario: Filter by date window
- **WHEN** a date range is provided
- **THEN** only events within the requested window are returned

### Requirement: Capture operator feedback
The system SHALL allow internal users to submit feedback on events or digests for later relevance tuning and quality improvement.

#### Scenario: Submit feedback record
- **WHEN** an internal user submits event feedback
- **THEN** the system records the feedback with target id, type, and timestamp
