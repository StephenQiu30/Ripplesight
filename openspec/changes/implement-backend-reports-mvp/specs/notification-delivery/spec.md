## MODIFIED Requirements

### Requirement: Report notification records

The system SHALL record SMTP delivery status for reports without blocking report generation.

#### Scenario: SMTP missing

- **WHEN** a report send is requested without SMTP configuration
- **THEN** a notification record is created with status `skipped`
- **AND** the report remains available

#### Scenario: SMTP failure

- **WHEN** SMTP sending fails
- **THEN** a notification record is created with status `failed`
- **AND** the error message is recorded
