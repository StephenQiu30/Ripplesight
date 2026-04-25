## MODIFIED Requirements

### Requirement: Hotspot storage and retrieval

#### Scenario: Filtered hotspot status

- **WHEN** a newly analyzed hotspot is below the relevance threshold
- **THEN** the system stores or updates it with status `filtered`

#### Scenario: Active hotspot status

- **WHEN** a newly analyzed hotspot meets the relevance threshold
- **THEN** the system stores or updates it with status `active`
