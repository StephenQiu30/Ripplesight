## MODIFIED Requirements

### Requirement: Immediate cross-source search

The system SHALL provide immediate cross-source search without persisting hotspot records.

#### Scenario: Default sources available

- **WHEN** immediate search runs in an empty database
- **THEN** default source definitions are available before loading enabled sources

#### Scenario: Search remains read-only

- **WHEN** immediate search returns analyzed results
- **THEN** no hotspot, AI analysis, or notification records are created

#### Scenario: Search source failure

- **WHEN** one source fails during immediate search
- **THEN** the API returns results from other sources
- **AND** includes source error details
