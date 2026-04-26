## MODIFIED Requirements

### Requirement: Hotspot storage and retrieval

The system SHALL store analyzed hotspot status as active or filtered according to the configured relevance threshold.

#### Scenario: Filtered hotspot status

- **WHEN** a newly analyzed hotspot is below the relevance threshold
- **THEN** the system stores or updates it with status `filtered`

#### Scenario: Active hotspot status

- **WHEN** a newly analyzed hotspot meets the relevance threshold
- **THEN** the system stores or updates it with status `active`
