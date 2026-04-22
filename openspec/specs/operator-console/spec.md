## Purpose

Define the internal console workflows for browsing hotspots, inspecting event details, tracing source evidence, searching history, and recording operator feedback.

## Requirements

### Requirement: Browse today's hotspot ranking
The system SHALL provide an operator console view for browsing the current hotspot ranking.

#### Scenario: View today's hotspot list
- **WHEN** an internal user opens the hotspot ranking view
- **THEN** the system returns the paginated event list for the current ranked hotspot set

#### Scenario: Filter hotspot list by topic or source type
- **WHEN** an internal user applies supported topic or source filters
- **THEN** the system returns the filtered hotspot list using the shared pagination structure

### Requirement: Inspect hotspot event details and source trace
The system SHALL provide a detail view for each hotspot event with event summary, source count, and traceable evidence links.

#### Scenario: Open event details
- **WHEN** an internal user requests a specific hotspot event
- **THEN** the system returns the event detail payload for that event identifier

#### Scenario: Review source trace
- **WHEN** the event detail view is displayed
- **THEN** the system exposes the source evidence chain needed to inspect where the event came from

### Requirement: Search and filter recent hotspot history
The system SHALL support keyword search and time-based filtering across hotspot events and related summaries.

#### Scenario: Search by keyword
- **WHEN** an internal user submits a search query
- **THEN** the system returns matching hotspot events in a paginated search response

#### Scenario: Filter by date window
- **WHEN** an internal user requests a date-bounded event view
- **THEN** the system limits the returned hotspot events to the requested date range

### Requirement: Capture operator feedback
The system SHALL allow internal users to submit feedback on events or digests for later relevance tuning and quality improvement.

#### Scenario: Submit event feedback
- **WHEN** an internal user submits feedback for a hotspot event
- **THEN** the system records the feedback with the target type, target identifier, feedback type, and creation time

#### Scenario: Use feedback as an optimization input
- **WHEN** feedback records are stored
- **THEN** the system preserves them for future weighting, tuning, or quality-review workflows
