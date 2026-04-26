## ADDED Requirements

### Requirement: Unified reports

The system SHALL expose daily and weekly reports through `/api/reports`.

#### Scenario: Daily report

- **WHEN** an operator creates a daily report
- **THEN** the system stores a `daily` report for the requested or default day
- **AND** includes only active hotspots in that UTC day

#### Scenario: Weekly report

- **WHEN** an operator creates a weekly report
- **THEN** the system stores a `weekly` report for the requested or default ISO week
- **AND** includes only active hotspots in that week

#### Scenario: Old daily report API removed

- **WHEN** the OpenAPI schema is generated
- **THEN** `/api/reports` routes are present
- **AND** `/api/daily-reports` routes are absent

#### Scenario: Empty report

- **WHEN** no active hotspots exist in the report period
- **THEN** the system still generates a report explaining that no matching hotspots were found
