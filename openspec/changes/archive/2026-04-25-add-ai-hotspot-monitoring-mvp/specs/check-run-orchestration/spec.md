## ADDED Requirements

### Requirement: Shared check-run pipeline

The system shall use one orchestration path for manual and scheduled hotspot checks.

#### Scenario: Manual trigger

- **WHEN** an operator calls the manual check-run API
- **THEN** the system creates a `check_runs` record
- **AND** executes the source, AI, hotspot, and notification workflow

#### Scenario: Scheduled trigger

- **WHEN** the lightweight scheduler interval elapses
- **THEN** the system invokes the same workflow with trigger type `scheduled`
