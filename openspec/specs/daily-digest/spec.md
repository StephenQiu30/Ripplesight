## Purpose

Define how analyzed hotspots are summarized into template-based daily reports and delivered by email.

## Requirements

### Requirement: Daily report generation

The system SHALL generate one daily report for a selected date from active analyzed hotspots.

#### Scenario: Generate report with hotspots

- **WHEN** an operator requests a daily digest for a date with analyzed hotspots
- **THEN** the system stores a `reports` record with `report_type` equal to `daily`
- **AND** the report includes a subject, summary, content, hotspot count, and selected hotspot details

#### Scenario: Generate empty report

- **WHEN** an operator requests a daily digest for a date with no analyzed hotspots
- **THEN** the system stores a `reports` record with `report_type` equal to `daily` and `hotspot_count` equal to `0`
- **AND** the report content clearly states that no hotspots were found

#### Scenario: Regenerate existing date

- **WHEN** a report already exists for the requested date
- **THEN** the system refreshes that report instead of inserting a duplicate date record

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
