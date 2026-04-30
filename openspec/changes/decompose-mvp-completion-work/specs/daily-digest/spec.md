## MODIFIED Requirements

### Requirement: Daily report generation
The system SHALL generate one template-based daily report for a selected date from active analyzed hotspots.

#### Scenario: Generate report with hotspots
- **WHEN** an operator requests a daily report for a date with active analyzed hotspots
- **THEN** the system stores a `reports` record with `report_type` equal to `daily`
- **AND** the report includes a subject, summary, content, hotspot count, and selected hotspot details

#### Scenario: Generate empty report
- **WHEN** an operator requests a daily report for a date with no active analyzed hotspots
- **THEN** the system stores a `reports` record with `report_type` equal to `daily` and `hotspot_count` equal to `0`
- **AND** the report content clearly states that no hotspots were found

#### Scenario: Regenerate existing date
- **WHEN** a report already exists for the requested date
- **THEN** the system refreshes that report instead of inserting a duplicate date record

#### Scenario: Filtered hotspots are excluded
- **WHEN** a daily report is generated
- **THEN** hotspots with status `filtered` are not included
- **AND** only `active` hotspots contribute to `hotspot_count`

### Requirement: Daily report email delivery
The system SHALL send a daily report by SMTP when configured and record delivery status.

#### Scenario: SMTP configured
- **WHEN** an operator sends an existing daily report and SMTP config exists
- **THEN** the system sends the digest email
- **AND** records a notification linked to the report

#### Scenario: SMTP missing
- **WHEN** an operator sends an existing daily report and SMTP config is missing
- **THEN** the system records a skipped notification
- **AND** the API call does not fail because of missing SMTP config

### Requirement: Daily report retrieval
The system SHALL expose list and detail APIs for generated reports.

#### Scenario: List reports
- **WHEN** an operator lists reports
- **THEN** the API returns reports ordered by report date descending

#### Scenario: Read report detail
- **WHEN** an operator requests one daily report by id
- **THEN** the API returns the stored subject, summary, content, status, hotspot count, and timestamps

## ADDED Requirements

### Requirement: Weekly report generation
The system SHALL generate one template-based weekly report for an ISO week from active analyzed hotspots.

#### Scenario: Generate weekly report
- **WHEN** an operator requests a weekly report for a week with active analyzed hotspots
- **THEN** the system stores a `reports` record with `report_type` equal to `weekly`
- **AND** the report period covers Monday 00:00:00 through the following Monday 00:00:00

#### Scenario: Weekly report excludes filtered hotspots
- **WHEN** a weekly report is generated
- **THEN** hotspots with status `filtered` are not included
- **AND** only `active` hotspots contribute to `hotspot_count`

### Requirement: Template-first report content
The system SHALL treat local Markdown template rendering as the P0 report baseline and SHALL NOT require AI-generated full-report content for MVP acceptance.

#### Scenario: Model is not configured
- **WHEN** report generation runs without an OpenAI-compatible model configured
- **THEN** the system generates a Markdown report from the local template
- **AND** report generation succeeds without model access

#### Scenario: Future AI report enhancement fails
- **WHEN** a future AI report enhancement fails
- **THEN** the system falls back to the local Markdown template
- **AND** report generation does not fail solely because of the enhancement failure
