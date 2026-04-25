## ADDED Requirements

### Requirement: Generate and persist one daily digest
The system SHALL generate one AI hotspot digest per day and persist its key metadata for traceable delivery.

#### Scenario: Produce daily digest payload
- **WHEN** the daily schedule for target date triggers
- **THEN** the system creates a digest record with event list, ordered ranking, and generation timestamp

#### Scenario: Persist digest generation metadata
- **WHEN** the digest is produced
- **THEN** the system records generation status, digest date, and generation source list

## MODIFIED Requirements

### Requirement: Summarize events in Chinese with evidence context
The system SHALL produce Chinese summaries for digest events while preserving the evidence context needed for later verification.

#### Scenario: Generate Chinese summary for ranked events
- **WHEN** a hotspot event is prepared for digest inclusion
- **THEN** the system generates a Chinese summary and keeps source evidence context in the same payload

#### Scenario: Keep per-event evidence alongside text summary
- **WHEN** a digest is assembled
- **THEN** each event block contains source links or evidence identifiers

### Requirement: Deliver the digest through email
The system SHALL deliver the daily digest through the configured email channel as the MVP delivery path.

#### Scenario: Send digest and record transport status
- **WHEN** digest generation completes
- **THEN** the system sends the configured recipient digest email and stores delivery status (`pending`, `sent`, `failed`)

#### Scenario: Keep status traceability after send
- **WHEN** delivery returns success or failure
- **THEN** the system records attempt time, recipient, status code, and failure reason when applicable

### Requirement: Isolate failures in the digest workflow
The system SHALL isolate upstream source or summarization failures so that a single dependency issue does not automatically prevent the entire digest workflow from completing.

#### Scenario: Continue digest build when one item fails
- **WHEN** one supporting item cannot be summarized or one source adapter fails
- **THEN** the digest workflow still delivers remaining ranked events and marks degraded items
