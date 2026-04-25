## MODIFIED Requirements

### Requirement: Candidate AI analysis

#### Scenario: Query expansion

- **WHEN** a keyword is used for hotspot monitoring
- **THEN** the system expands it into related search queries before fetching source candidates

#### Scenario: Relevance threshold

- **WHEN** a hotspot analysis has relevance below `RELEVANCE_THRESHOLD`
- **THEN** the hotspot is marked `filtered`
- **AND** it is excluded from event email and daily digest delivery

#### Scenario: Active hotspot

- **WHEN** a hotspot analysis has relevance at or above `RELEVANCE_THRESHOLD`
- **THEN** the hotspot is marked `active`
- **AND** it can be shown, notified, and included in daily digest content
