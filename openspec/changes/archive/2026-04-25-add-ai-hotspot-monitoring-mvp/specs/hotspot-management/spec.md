## ADDED Requirements

### Requirement: Hotspot storage and retrieval

The system shall store deduplicated hotspots and expose list and detail APIs with filtering and sorting.

#### Scenario: Duplicate source URL

- **WHEN** a candidate has the same `source_id` and `url` as an existing hotspot
- **THEN** the system does not insert a duplicate hotspot

#### Scenario: Filter hotspot list

- **WHEN** an operator filters by keyword, source, importance, or time range
- **THEN** the API returns matching hotspots with pagination
