## ADDED Requirements

### Requirement: Immediate cross-source search

The system shall provide an API to search multiple sources immediately for one query and return analyzed results.

#### Scenario: Search query

- **WHEN** an operator submits a query to `/api/search`
- **THEN** the system fetches candidates from enabled or requested sources
- **AND** returns analyzed results without requiring keyword persistence

#### Scenario: Search source failure

- **WHEN** one source fails during immediate search
- **THEN** the API returns results from other sources
- **AND** includes source error details
