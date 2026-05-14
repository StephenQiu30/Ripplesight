## MODIFIED Requirements

### Requirement: SMTP notification records
The system SHALL send SMTP email notifications when configured and always record notification status for hotspot events and reports.

#### Scenario: SMTP configured
- **WHEN** a qualifying hotspot is produced and SMTP config exists
- **THEN** the system sends an email containing title, summary, source link, and relevance reason
- **AND** records a successful notification

#### Scenario: SMTP missing
- **WHEN** SMTP config is missing
- **THEN** the system skips email sending
- **AND** records a skipped notification without failing the check run

#### Scenario: Report notification
- **WHEN** a daily or weekly report email is sent, skipped, or fails
- **THEN** the system records a notification linked to `report_id`
- **AND** does not require a hotspot id for that notification

#### Scenario: Filtered hotspot notification is blocked
- **WHEN** a hotspot is marked `filtered`
- **THEN** the system does not send an event email for that hotspot
- **AND** no successful event notification is recorded for that filtered hotspot
