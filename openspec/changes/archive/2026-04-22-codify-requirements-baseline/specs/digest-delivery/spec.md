## ADDED Requirements

### Requirement: Generate a daily ranked digest
The system SHALL generate one AI hotspot digest per day from the ranked hotspot event set.

#### Scenario: Produce the daily digest
- **WHEN** the daily digest workflow runs for the target date
- **THEN** the system creates a digest record containing the selected hotspot events and generation timestamp

#### Scenario: Use ranked events as digest input
- **WHEN** the digest is assembled
- **THEN** the system orders digest content according to the hotspot ranking outcome instead of arbitrary source order

### Requirement: Summarize events in Chinese with evidence context
The system SHALL produce Chinese summaries for digest events while preserving the evidence context needed for later verification.

#### Scenario: Generate a Chinese event summary
- **WHEN** a hotspot event is prepared for digest inclusion
- **THEN** the system generates a Chinese summary for that event

#### Scenario: Preserve evidence alongside summaries
- **WHEN** the digest content is generated
- **THEN** the resulting digest retains links or references to the supporting source evidence for each event

### Requirement: Deliver the digest through email
The system SHALL deliver the daily digest through the configured email channel as the MVP delivery path.

#### Scenario: Send the daily digest email
- **WHEN** a digest is ready for delivery
- **THEN** the system sends the digest through the configured email delivery provider

#### Scenario: Track delivery status
- **WHEN** the delivery attempt completes
- **THEN** the system records the digest delivery status for operational follow-up

### Requirement: Isolate failures in the digest workflow
The system SHALL isolate upstream source or summarization failures so that a single dependency issue does not automatically prevent the entire digest workflow from completing.

#### Scenario: Handle partial upstream failure
- **WHEN** one source adapter or one summary generation step fails during digest preparation
- **THEN** the system continues the digest workflow with the remaining available event set and records the degraded condition
