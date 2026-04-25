## MODIFIED Requirements

### Requirement: Configurable content sources
The system SHALL allow operators to register and manage content sources with explicit source type, access method, language, region, weight, polling interval, and enabled state.

#### Scenario: List enabled source configs for MVP run
- **WHEN** an operator requests source configurations for runtime execution
- **THEN** the system returns only currently enabled source records with source type, access method, language, region, weight, polling interval, and enabled state

#### Scenario: Disable a source and skip it from scheduler input
- **WHEN** a source is marked as disabled
- **THEN** the system excludes that source from subsequent ingestion scheduling until it is re-enabled

### Requirement: Enforce source inclusion boundaries
The system SHALL enforce the agreed MVP source policy by prioritizing structured public sources and excluding unsupported high-cost or high-risk collection paths from the main workflow.

#### Scenario: Keep source set within approved classes for MVP
- **WHEN** the ingestion platform is configured for MVP operation
- **THEN** the active source set is limited to approved public-source categories defined by PRD scope

#### Scenario: Reject unsupported non-primary X collection path
- **WHEN** an operator configures third-party scraping as the default X path
- **THEN** the system marks this path as out of scope and does not add it to the active execution plan

### Requirement: Govern X keyword monitoring rules
The system SHALL maintain configurable X keyword rules for AI companies, models, events, and industry topics within the official X API boundary.

#### Scenario: Review keyword rules before execution
- **WHEN** an operator requests the X keyword rule list
- **THEN** the system returns configured keyword rules and active status for execution audit

### Requirement: Govern monitored X accounts
The system SHALL maintain a monitored-account registry for official AI company accounts, founders, research leaders, and other high-signal actors.

#### Scenario: Persist monitored account metadata in governance records
- **WHEN** a monitored account is used in source collection
- **THEN** the system retains account metadata for downstream scoring and evidence tracing
