## MODIFIED Requirements

### Requirement: Lightweight scheduled reports

The scheduler SHALL optionally generate daily and weekly reports using the same backend report service.

#### Scenario: Daily scheduled report

- **WHEN** daily report scheduling is enabled and the configured hour has passed
- **THEN** the scheduler generates and sends yesterday's daily report once

#### Scenario: Weekly scheduled report

- **WHEN** weekly report scheduling is enabled and the configured weekday/hour has passed
- **THEN** the scheduler generates and sends the previous complete ISO week report once
