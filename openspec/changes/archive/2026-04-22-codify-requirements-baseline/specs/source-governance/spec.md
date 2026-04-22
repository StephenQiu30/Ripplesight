## ADDED Requirements

### Requirement: Configurable content sources
The system SHALL allow operators to register and manage content sources with explicit source type, access method, language, region, weight, polling interval, and enabled state.

#### Scenario: List configured sources
- **WHEN** an operator requests the source configuration list
- **THEN** the system returns paginated source records with their configuration fields and enabled state

#### Scenario: Disable a source
- **WHEN** a source is marked as disabled
- **THEN** the system excludes that source from subsequent ingestion scheduling until it is re-enabled

### Requirement: Govern X keyword monitoring rules
The system SHALL maintain configurable X keyword rules for AI companies, models, events, and industry topics within the official X API boundary.

#### Scenario: Review keyword rules
- **WHEN** an operator requests the X keyword rule list
- **THEN** the system returns the configured keyword rules and their active status

#### Scenario: Execute keyword monitoring
- **WHEN** keyword-based X monitoring runs
- **THEN** the system uses only enabled rules and searches within the supported recent-search window

### Requirement: Govern monitored X accounts
The system SHALL maintain a monitored-account registry for official AI company accounts, founders, research leaders, and other high-signal actors.

#### Scenario: Review monitored accounts
- **WHEN** an operator requests the monitored account list
- **THEN** the system returns the configured handles, account metadata, weights, and active status

#### Scenario: Use monitored accounts as first-hand signals
- **WHEN** content is collected from a monitored account
- **THEN** the system preserves the originating account metadata for downstream scoring and evidence tracing

### Requirement: Enforce source inclusion boundaries
The system SHALL enforce the agreed MVP source policy by prioritizing structured public sources and excluding unsupported high-cost or high-risk collection paths from the main workflow.

#### Scenario: Use approved source classes
- **WHEN** the ingestion platform is configured for MVP operation
- **THEN** the active source set is limited to the approved public-source categories defined by the baseline documents

#### Scenario: Reject unsupported X scraping as a primary path
- **WHEN** an operator attempts to define third-party X scraping as the main X ingestion method for MVP
- **THEN** the system treats that configuration as out of scope for the baseline workflow
