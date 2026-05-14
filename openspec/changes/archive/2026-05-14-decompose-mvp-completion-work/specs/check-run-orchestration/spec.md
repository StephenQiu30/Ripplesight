## MODIFIED Requirements

### Requirement: Shared check-run pipeline
The system SHALL use one orchestration path for manual and scheduled hotspot checks.

#### Scenario: Manual trigger
- **WHEN** an operator calls the manual check-run API
- **THEN** the system creates a `check_runs` record
- **AND** executes the source, AI, hotspot, and notification workflow

#### Scenario: Scheduled trigger
- **WHEN** the lightweight scheduler interval elapses
- **THEN** the system invokes the same workflow with trigger type `scheduled`

#### Scenario: Source errors are summarized
- **WHEN** one or more sources fail or are skipped during a check run
- **THEN** the check run records an error summary
- **AND** successful candidate processing from other sources can still complete

#### Scenario: Scheduled reports share report service
- **WHEN** scheduled daily or weekly report generation is enabled
- **THEN** the scheduler uses the same report service as manual report generation
- **AND** SMTP missing or failed delivery does not roll back report generation
