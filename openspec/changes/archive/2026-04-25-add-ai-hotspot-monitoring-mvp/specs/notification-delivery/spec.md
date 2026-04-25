## ADDED Requirements

### Requirement: SMTP notification records

The system shall send SMTP email notifications when configured and always record notification status.

#### Scenario: SMTP configured

- **WHEN** a qualifying hotspot is produced and SMTP config exists
- **THEN** the system sends an email containing title, summary, source link, and relevance reason
- **AND** records a successful notification

#### Scenario: SMTP missing

- **WHEN** SMTP config is missing
- **THEN** the system skips email sending
- **AND** records a skipped notification without failing the check run
