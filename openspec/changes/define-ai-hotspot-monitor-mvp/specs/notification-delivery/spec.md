## MODIFIED Requirements

### Requirement: SMTP notification records

The system SHALL send event email only for active hotspots and avoid event email for filtered hotspots.

#### Scenario: Active-only event email

- **WHEN** a newly analyzed hotspot is below the relevance threshold
- **THEN** no event email is sent for that hotspot

#### Scenario: Active event email

- **WHEN** a newly analyzed hotspot meets the relevance threshold and SMTP is configured
- **THEN** the system sends an event email and records notification status
