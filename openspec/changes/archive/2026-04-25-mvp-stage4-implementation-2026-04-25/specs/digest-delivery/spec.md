## MODIFIED Requirements

### Requirement: Generate a daily ranked digest
The system SHALL generate one AI hotspot digest per day from the ranked hotspot event set and retain references for downstream verification.

#### Scenario: Produce the daily digest
- **WHEN** the daily digest workflow runs for the target date
- **THEN** the system creates a digest record containing the ranked event ids and highlights
- **AND** selection and order follow the ranked event stream produced in earlier phases

#### Scenario: Include the digest input window
- **WHEN** `get_today_digest` is executed
- **THEN** the system uses the current configured daily event set as source without changing API contracts

### Requirement: Summarize events in Chinese with evidence context
The system SHALL produce Chinese summaries for digest events and attach verifiable evidence references for each event line.

#### Scenario: Generate an event digest line in Chinese
- **WHEN** a hotspot event is prepared for digest inclusion
- **THEN** the digest line SHALL include a Chinese summary and event score
- **AND** it SHALL preserve existing event source evidence references

#### Scenario: Render event evidence links
- **WHEN** rendering digest email body
- **THEN** each digest event SHALL show at least one evidence link or a reason when evidence is unavailable

### Requirement: Deliver the digest through email
The system SHALL deliver the daily digest through the configured email channel as the MVP delivery path and persist the delivery status.

#### Scenario: Send the daily digest email
- **WHEN** a digest is rendered
- **THEN** the system sends the digest through the configured email delivery provider
- **AND** records `delivered`, `partial`, or `failed` status according to execution outcome

#### Scenario: Track delivery status for degraded rendering
- **WHEN** digest rendering succeeds with partial event failures
- **THEN** the system records a degraded delivery status (`partial`)

### Requirement: Isolate failures in the digest workflow
The system SHALL isolate upstream or per-event failures so that a single dependency issue does not block the entire digest workflow.

#### Scenario: Handle partial event rendering failure
- **WHEN** one event has malformed data during digest rendering
- **THEN** the system excludes or degrades only that event and continues rendering other events

#### Scenario: Handle complete render failure
- **WHEN** digest rendering fails at an unrecoverable level
- **THEN** the system generates a minimal fallback body and still attempts delivery
- **AND** records a failed render status when fallback also fails
