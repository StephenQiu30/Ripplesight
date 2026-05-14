## MODIFIED Requirements

### Requirement: Candidate AI analysis

The system SHALL classify analyzed candidates as `active` only when relevance meets the configured threshold and AI truthfulness is not explicitly false, while supporting threshold/realism filtering.

#### Scenario: False result is filtered

- **WHEN** AI analysis returns `is_real` as false
- **AND** relevance is at or above `RELEVANCE_THRESHOLD`
- **THEN** the result is classified as `filtered`

#### Scenario: Relevant real result is active

- **WHEN** AI analysis relevance is at or above `RELEVANCE_THRESHOLD`
- **AND** `is_real` is not false
- **THEN** the result is classified as `active`
