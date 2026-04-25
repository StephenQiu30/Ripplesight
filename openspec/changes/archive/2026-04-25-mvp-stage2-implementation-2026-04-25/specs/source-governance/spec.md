## ADDED Requirements

### Requirement: Enforce source runtime eligibility before discovery
The system SHALL only pass governance-enabled sources into the discovery ingestion flow.

#### Scenario: Skip disabled source in discovery input
- **WHEN** discovery is executed with source configurations that include disabled entries
- **THEN** disabled sources are excluded from normalization and do not contribute raw or event records.

## MODIFIED Requirements

### Requirement: Configurable content sources
The system SHALL allow operators to register and manage content sources with explicit source type, access method, language, region, weight, polling interval, and enabled state.

#### Scenario: List configured sources
- **WHEN** an operator requests the source configuration list
- **THEN** the system returns paginated source records with their configuration fields and enabled state

#### Scenario: Disable a source
- **WHEN** a source is marked as disabled
- **THEN** the system excludes that source from subsequent ingestion scheduling until it is re-enabled
